# Resumen de Proyecto: Self-Extending Agent con LangGraph y MCP

Este documento sintetiza la arquitectura, los componentes clave y, sobre todo, **los aprendizajes críticos y soluciones de errores** que hemos implementado en el desarrollo de este agente autónomo basado en LangGraph y MCP (Model Context Protocol). Es ideal para contextualizar a un agente de IA en futuras sesiones.

## 1. Arquitectura General y Orquestación (LangGraph)

El proyecto utiliza **LangGraph** para construir un sistema multi-agente orquestado jerárquicamente. 
- **Supervisor:** Actúa como el enrutador principal (`_build_graph` en `main.py`). Analiza la petición del usuario y usa un modelo Pydantic dinámico (`Route`) para delegar el trabajo al sub-agente más adecuado.
- **Sub-Agentes Dinámicos:** Los agentes (ej: `mcp`, `researcher`, `assistant`) se descubren automáticamente en la carpeta `sub_agents/` leyendo archivos que heredan de `BaseSubAgent`.
- **Hot-Reload:** El sistema puede detectar nuevos agentes añadidos en tiempo de ejecución y recompilar el grafo sin tener que reiniciar la sesión completa de terminal.

## 2. Integración de Herramientas Externas (MCP Client)

El verdadero poder del sistema reside en `mcp_client.py`, el gestor que se conecta a múltiples servidores MCP externos (definidos en `mcp_config.yaml`):
- **Servidores actuales:** `github` (vía `mcp-remote` hacia Cloud Run) y `faqs` (API de Apprecio).
- **Proceso:** El cliente inicializa subprocesos proxy `stdio`, se conecta a los servidores remotos vía HTTP/SSE (`mcp-remote`), solicita la lista de herramientas disponibles (`tools/list`) y se las provee a LangChain como funciones invocables asíncronas.

---

## 3. Lecciones Aprendidas y Bugs Solucionados (CRÍTICO)

A lo largo del desarrollo nos topamos con serios obstáculos de arquitectura que fuimos solventando. Si en el futuro notas regresiones, revisa estos puntos:

### A. Condición de Carrera (Race Condition) en Inicialización MCP
* **Problema:** El sistema intentaba recuperar las herramientas de los servidores MCP (`get_all_tools()`) **antes** de que la conexión asíncrona STDIO↔SSE estuviera completamente lista, resultando en un agente MCP sin herramientas.
* **Solución:** Abandonamos los `asyncio.sleep()` de tiempo fijo e implementamos el uso de **`asyncio.Event`** (`ready_event`) en `mcp_client.py`. Ahora el cliente espera estrictamente el mensaje de handshake de inicialización de RPC antes de pedir las herramientas.

### B. El Supervisor Sobrescribiendo Tareas / Ciclos Infinitos
* **Problema:** En LangGraph, si un nodo (como un sub-agente) termina su trabajo, originalmente volvíamos al Supervisor, y éste a veces intentaba responder usando LLM de nuevo (sobrescribiendo el output real de la herramienta con un resumen pobre) o finalizaba usando un canal inválido (`FINISH`).
* **Solución:**
  1. Corregimos el ruteo condicional (`supervisor_condition` y mapas condicionales de validación de LangGraph).
  2. Implementamos una funcionalidad de **passthrough**: Cuando el Supervisor nota que acaba de volver de un nodo "Worker" (ej: ya trajo la información de los repositorios), se salta la llamada al LLM y retorna `{"next_node": "END"}`, terminando exitosamente el grafo y mostrando el output original del Worker al usuario.

### C. Bias Ciego del Supervisor (Límites de Contexto)
* **Problema:** Al agregar el servidor MCP de Apprecio, el Supervisor no lo utilizaba y prefería usar al Agente "Researcher" para buscar dudas en Google.
* **Causa:** En `mcp_agent.py`, para evitar saturar el prompt del Supervisor, estábamos truncando la exposición dinámica de herramientas a las primeras 30 (`[:30]`). Como GitHub inyectaba más de 40 herramientas, **las herramientas de Apprecio quedaban invisibles** para el Supervisor.
* **Solución:**
  1. Elevamos el truncamiento visual a las primeras 100 herramientas.
  2. Creamos el método **`set_tools()`** en `BaseSubAgent` que inyecta dinámicamente las herramientas *antes* de armar el Supervisor en `main.py`.
  3. Modificamos los Prompts del Supervisor en `main.py` y del propio `researcher_agent.py`, declarando explícitamente jerarquías: *"El MCP es el cerebro interno de la empresa. El Researcher es el Último Recurso de muy baja prioridad"*.

### D. Crash de la Aplicación por Excepciones de APIs Externas
* **Problema:** Cuando una herramienta MCP devolvía una excepción (ej: Error 404 al buscar un repositorio en Github, o un 500), la excepción volaba directamente hacia LangGraph (la librería core), rompiendo todo el loop de eventos de Asyncio y matando la terminal.
* **Intento 1:** Envolvimos en `mcp_client.py` con un simple `try-except` que devolvía un string amigable para que el LLM lo leyese y corrigiera su rumbo en el siguiente loop. ¡Explotó otra vez!
* **La Solución Real y Compleja:** Al volver el output en forma de String, estábamos rompiendo la estructura de retorno estricta. Las herramientas envueltas por librerías nativas suelen declarar un `response_format='content_and_artifact'`, que le exige a Python retornar siempre una **tupla** `(mensaje, artefacto)`. 
Modificamos nuestra capa defensiva (wrapper dinámico en `mcp_client.py`) para revisar el `response_format` declarado en cada herramienta y retornar `(err_msg, None)` en caso de error asíncrono. Ahora el framework resiste cualquier API caída.

### E. Hot-Reload y Corrupción del Import Cache (`sys.modules`)
* **Problema:** Queríamos que al crear un nuevo agente (`ej: fitness_agent.py`) desde el chat, el sistema lo descubriera sin reiniciar. Al usar `importlib.reload()` o vaciar sub-módulos, las importaciones relativas (ej: `from .base import BaseSubAgent`) dejaban de funcionar ("attempted relative import with no known parent package").
* **Solución:** Modificamos `_check_and_reload_graph()` en `main.py` para eliminar de `sys.modules` **solo** los módulos hijos (ej: `agent_core.sub_agents.fitness_agent`) y usar `importlib.import_module` de forma estándar en el discovery, **conservando el módulo padre** (`agent_core.sub_agents`). Esto preserva el contexto del paquete y permite recompilar dinámicamente el grafo de LangGraph conectando los nuevos sub-agentes en caliente.

### F. FINISH Prematuro del Supervisor (Tool Calls Abortadas)
* **Problema:** Las herramientas MCP (o cualquier tool) nunca llegaban a ejecutarse. El log mostraba la intención del LLM de usar la herramienta (`[mcp decide usar herramienta]`), pero el Supervisor tomaba el control inmediatamente y terminaba la ejecución con `FINISH`.
* **Causa:** El `supervisor_node` evaluaba si el último mensaje era generado por la IA (`messages[-1].type == "ai"`) para dar por concluido el trabajo del worker. No contemplaba que un mensaje "ai" podía contener un **petición de herramienta** (`tool_calls`) pendiente de ser procesada por un `ToolNode`.
* **Solución:** Ajustamos la condición temprana del supervisor para revisar explícitamente `hasattr(messages[-1], "tool_calls")`. Si el worker emite un mensaje con tool calls, el supervisor *se salta* su evaluación para permitir que el flujo de LangGraph vaya al nodo de herramientas (`create_worker_condition`).

### G. Confusión Cognitiva del Dev Agent vs Herramientas Externas
* **Problema:** El "Dev Agent" tenía acceso tanto a herramientas locales de creación de scripts como a herramientas MCP de GitHub. Cuando se le pedía leer un repositorio, el LLM intentaba escribir un script Python local usando `requests` en vez de usar la tool nativa de GitHub MCP.
* **Solución:** Desacoplamos las responsabilidades. Creamos un **`McpAgent` dedicado** que intercepta dinámicamente TODAS las herramientas provenientes de servidores externos (filtrando las herramientas locales en español). Luego, ajustamos el Prompt instruyendo al sistema a delegar tareas de APIs / GitHub exclusivamente a este nuevo agente.

### H. Eliminación Segura y Completa de Sub-Agentes
* **Problema:** Los usuarios querían borrar sub-agentes obsoletos (ej. `fitness`), pero solo desvincular la clase no borraba los archivos asociados (bases de datos, CSVs, memoria), dejando el proyecto lleno de basura.
* **Solución:** Instructurar formalmente al `dev_agent` en su System Prompt con un flujo de limpieza seguro. Siempre que le piden eliminar un agente, el `dev` usa primero un script local rápido para examinar los archivos del agente, identifica todas sus dependencias y finalmente invoca iterativamente la herramienta predeterminada `eliminar_archivo_en_proyecto` (actualizada para soportar `shutil.rmtree()` sobre directorios) borrando el módulo absoluto del disco.

### I. Arquitectura de Carpetas y Módulos por Agente (Isolation)
* **Problema:** Las raíces de los agentes estaban creando un desorden al producir archivos CSVs o txts globales si se desarrollaban como un único `archivo_agent.py`.
* **Solución:** Actualizamos el discovery de `main.py` (`_get_sub_agents_snapshot` y `discover_sub_agents`) para que soporte tanto archivos sueltos `sub_agents/ejemplo.py` como también componentes encapsulados en su propia carpeta: `sub_agents/ejemplo/ejemplo_agent.py`. Ahora los nuevos scripts ordenan su mundo escribiendo en carpetas como `sub_agents/<nombre>/files/`.

### J. Segmentación de Memoria (Episódica y Procedimental) Independiente
* **Problema:** Si el usuario le decía "Me llamo Jesús" o le pasaba contextos globales, esto llenaba el prompt de TODOS los sub-agentes, aumentando el coste y el riesgo de saturación general por ruido.
* **Solución:** Actualizamos `memory_utils.py` y `make_agent_node` para que soporten la inyección compartida + la inyección individualizada. Pasamos el `agent_name` directamente del nombre del nodo del grafo a las funciones lectoras de memoria. Si la carpeta `sub_agents/<nombre>/episodica/` tiene archivos Markdown aislados, se añaden únicamente a su system prompt.

### K. Seguridad de Caracteres y Compatibilidad ASCII
* **Problema:** El uso de caracteres especiales (acentos, ñ, emojis) en nombres de agentes o dentro del código Python de los sub-agentes (como el de Theology) generaba inconsistencias en la detección y posibles errores de codificación en ciertos entornos.
* **Solución:** Establecimos la directiva de usar exclusivamente caracteres ASCII básicos (a-z) para nombres de archivos, clases e identificadores de agentes. Además, instruimos al `dev_agent` para evitar acentos incluso en docstrings y prompts internos de los sub-agentes generados, garantizando un funcionamiento robusto en cualquier terminal o sistema operativo.

---

## 4. Estructura de Archivos Clave

- `agent_core/main.py`: Cerebro del orquestador, definiciones de estado de LangGraph, filtros de enrutamiento dinámico y Hot-Reload.
- `agent_core/mcp_client.py`: Clase administradora, proxy asíncrono de los servidores MCP.
- `agent_core/sub_agents/base.py`: Arquitectura base de sub-agentes.
- `agent_core/sub_agents/mcp_agent.py`: Sub-agente especialista puro. Filtra tools locales y se queda solo con endpoints MCP externos.
- `agent_core/sub_agents/dev_agent.py`: Agente programador (autoreparable / escritor de scripts) que usa AutoCoder.
- `agent_core/mcp_config.yaml`: Archivo declarativo de servidores MCP.

## Próximos Pasos Sugeridos
* Agregar capas cognitivas más complejas a las memorias episódicas.
* Explorar la posibilidad de enviar credenciales (tokens) desde la lógica de la sesión en lugar del YAML para un entorno de multi-tenancy.
* Profundizar el uso de Agent-to-Agent (A2A) delegando tareas muy específicas a Swarms independientes creados en caliente.
