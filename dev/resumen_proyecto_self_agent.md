# Resumen de Proyecto: Leygo Agent (Self-Extending Agent con LangGraph y MCP)

Este documento sintetiza la arquitectura, los componentes clave y, sobre todo, **los aprendizajes críticos y soluciones de errores** del desarrollo de **Leygo**, un asistente de IA autónomo basado en LangGraph y el Model Context Protocol (MCP).

## 1. Arquitectura General: Sistema Multi-Agente Jerárquico
El proyecto ha evolucionado de un agente monolítico a una red de agentes especializados orquestados por LangGraph:
- **Supervisor Principal:** Actúa como el Director de Orquesta. Analiza el input (texto o voz) y decide a qué sub-agente delegar la tarea basándose en su descripción y capacidades.
- **Sub-Agentes Especializados (Discovery & Hot-Reload):** Leygo descubre automáticamente nuevos agentes en `agent_core/sub_agents/`. Soporta carga en caliente (hot-reload), permitiendo que el Supervisor aprenda nuevas habilidades o cambie su estructura sin reiniciar el sistema.
- **Modelos Dinámicos por Agente:** Cada sub-agente (`assistant`, `dev`, `mcp`, `researcher`, `autocoder`) consulta su propia variable de entorno (ej. `MODEL_DEV`) en el archivo `.env`. Si no se define o está vacía, el sistema _fallback_ de forma segura al modelo principal, otorgando máxima flexibilidad en el ratio costo/razonamiento por tarea.

## 2. Dockerización y Servicios
Para garantizar consistencia y facilitar el despliegue, el sistema está completamente contenedorizado:
- **leygo-bot:** Servicio FastAPI + `python-telegram-bot` que gestiona el núcleo de los agentes y la API REST para el frontend.
- **leygo-cli:** Interfaz de terminal interactiva para desarrollo y debugging.
- **leygo-gui:** Interfaz Frontend desarrollada en Angular 17+ (Signals, Standalone Components, temática Glassmorphism) servida para interactuar visualmente con el bot y gestionar agentes.
  - **Resolución Nginx SPA:** El `Dockerfile` del frontend incluye un archivo nativo `nginx.conf` que inyecta un `try_files $uri /index.html`. Esto evita los errores 404 de Nginx al refrescar (F5) páginas en la web app y transfiere el ruteo interno a la aplicación de Angular.
- **Persistencia:** Volúmenes de Docker vinculan todo el directorio `agent_core/` (incluyendo `memoria/` y `sub_agents/`), permitiendo que las ediciones de código y nuevos scripts se reflejen al instante (hot-reload) sin reconstruir la imagen de Docker.

## 3. Interfaz de Voz Nativa (Voz-a-Comando)
Una de las innovaciones clave es la integración de audio fluida en Telegram:
- **Flujo:** El bot detecta una nota de voz -> La descarga -> Gemini (ej. Flash o Lite) la transcribe de forma literal casi instantánea -> El texto resultante se inyecta directamente como input al sistema.
- **Resultado:** El usuario puede "hablarle" a Leygo. Leygo "escucha", entiende el comando y responde ejecutando las herramientas necesarias, eliminando la fricción de escribir.
- **Monitoreo:** Cada vez que una de estas transcripciones se ejecuta internamente, el gasto en tokens de imputa transparentemente dentro de la memoria administrativa como `Transcript Audio`.

---

## 4. Lecciones Aprendidas y Bugs Solucionados (CRÍTICO)

### A. Condición de Carrera en Inicialización MCP
* **Problema:** El sistema pedía herramientas antes de que el handshake RPC con los servidores remotos terminara.
* **Solución:** Implementación de `asyncio.Event` (`ready_event`) en `mcp_client.py`. El sistema espera estrictamente la señal de "Listo" de los servidores antes de continuar.

### B. El Supervisor Sobrescribiendo Tareas / Ciclos Infinitos
* **Problema:** El Supervisor intentaba resumir respuestas de sub-agentes especialistas, a menudo perdiendo precisión o entrando en loops.
* **Solución:** Patrón **Passthrough**. Si el flujo vuelve de un "Worker", el Supervisor simplemente pasa el resultado final al usuario y termina el grafo (`END`).

### C. Segmentación de Memoria (Episódica y Procedimental)
* **Problema:** Memorias globales saturaban el contexto de todos los agentes con información irrelevante.
* **Solución:** Aislamiento de memorias vía `memory_utils.py`. Cada agente tiene su propia subcarpeta `episodica/` y `procedimental/`. Leygo solo inyecta en el prompt la memoria relevante para el agente activo, reduciendo costos y aumentando la precisión.

### D. Seguridad de Caracteres y Escapes en Auto-Programación
* **Problema:** El `dev_agent` escapaba comillas (`\"\"\"`) al escribir código Python, generando archivos inválidos. También el uso de acentos en nombres de módulos rompía el discovery.
* **Solución:** 
  1. Directiva **"CERO ESCAPES"**: Instrucción de sistema prohibiendo escapes manuales; el sistema de archivos procesa el texto puro.
  2. Estandarización **ASCII**: Nombres de agentes y dependencias estrictamente en minúsculas y sin caracteres especiales.

### E. Crash por Excepciones en APIs Externas
* **Problema:** Un error 500 en un servidor MCP remoto mataba el loop de Asyncio.
* **Solución:** Implementación de un **Advanced Tool Wrapper** que revisa el `response_format` de LangChain. Si una API falla, el cliente captura el error y devuelve una tupla `(error_msg, None)`, permitiendo que el LLM procese el fallo sin colapsar el sistema.

### F. Sincronización Backend/Frontend y Renderizado en GUI
* **Problemas abordados:** 
  1. Pérdida del historial del chat al recargar la página.
  2. Textos de respuesta del LLM (Markdown) renderizados como texto plano sin formato.
  3. Agentes creados dinámicamente no aparecían de inmediato en la biblioteca del frontend.
* **Soluciones:**
  1. Integración de un State global basado en **Angular Signals** (`ChatService`) con backup en `LocalStorage`.
  2. Implementación de un Pipe de Angular usando la librería `marked` combinado con un bindeo por `[innerHTML]`, además de estilos CSS dedicados para evitar inyecciones e impulsar la estética UI.
  3. Reconfiguración de **Docker Compose** para montar la carpeta base completa y corrección de sintaxis y comillas escapadas en las docstrings de los agentes dinámicos generados por `dev_agent` para que el orquestador los lea sin romper la API REST de descubrimiento (`/api/agents`).

### G. Panel de Configuración e Inyección al Vuelo (.env)
* **Retos y Soluciones UI/API:** 
  1. **Hot Reload de Entorno:** FastAPI ahora expone el endpoint `/config` sin enmascarar valores, permitiendo la visualización directa (tipo `text`). Tras recibir actualizaciones, no solo sobrescribe `.env`, sino que actualiza `os.environ` y fuerza a `dotenv` a inyectar en memoria viva. Esto permite que el cambio del modelo LLM de un sub-agente (ej. de *Flash* a *Pro*) se aplique de inmediato sin resetear Docker.
  2. **Salto de Línea en Archivos Planos:** Se incluyó lógica predictiva en Python para verificar si un archivo `.env` terminado abruptamente requiere un salto de línea (`\\n`) previo a la inserción de una variable nueva, previniendo corrupción.
  3. **Angular Two-way Binding en Signals:** Se eliminó la inyección por defecto de Signals sobre `[(ngModel)]` en el front, sustituyendo `signal('')` por `string = ''`. Al interactuar con campos del tipo `ngModel` en Angular 17+, los Signals complejos eran destructurados, lanzando TypeError silenciosos que bloqueaban las peticiones de adición de key antes del envío.

### H. Alucinación de Herramientas (Tool Hallucination) en Workers LangGraph
* **Problema:** Un sub-agente (ej. `mcp`) colapsaba la ejecución alcanzando el "Recursion limit of 25" al intentar usar él mismo la herramienta `Route`. Esto sucedía porque leía el historial de mensajes compartido y creía, por imitación, que poseía la herramienta `Route` (la cual es exclusiva del Supervisor).
* **Solución:** Inyección de una directiva restrictiva estricta en el Prompt base de los workers (`make_agent_node`), prohibiendo explícitamente el uso de delegación o ruteo autónomo y forzándolos a delegar escribiendo texto en lenguaje natural para que el Supervisor lo intercepte.

### I. Cortocircuito de Orquestación (Zero-Shot Handoff Failure)
* **Problema:** En tareas multipaso (ej. "lee un archivo y luego manda correo"), el Supervisor delegaba al Agente MCP para leer... pero una vez que el MCP leía, el Supervisor cortaba el flujo asumiendo que el usuario ya estaba respondido, dejando el correo sin enviar.
* **Solución:** 
  1. Activación de Evaluación Continua: Se quitó el *short-circuit* manual que cortaba el grafo apenas el LLM respondía con texto. 
  2. Forzado Estricto de Sistema: Se configuró `tool_choice="any"` en el `bind_tools` del Supervisor, forzándolo a utilizar **siempre** la herramienta estructural `Route` (ya sea para seguir derivando iterativamente a otros sub-agentes, o usar `Route('FINISH')` para cerrar el ciclo limpiamente).

### J. Desfase Horario (Timezone Drift) en Scheduling (UTC vs Local)
* **Problema:** Tareas agendadas para "en 2 minutos" se ejecutaban con 3 horas de retraso. El contenedor en Docker opera en UTC. APScheduler estaba configurado para aislar el entorno en `America/Santiago`, pero el agente inyectaba objetos ingenuos (Naive Datetimes) creados con `datetime.now()`. APScheduler interpretaba malamente ese Naive Datetime UTC como si ya fuera Hora de Chile.
* **Solución:** Migración absoluta a Timezone-Aware Datetimes. Todo cálculo matemático temporal (`timedelta`) en `scheduler_manager.py` se genera inyectando forzosamente la zona horaria objetivo previa: `datetime.now(TIMEZONE)`.

## 5. Control de Costos y Uso de Tokens (Token Tracker)
Para habilitar una visibilidad completa de los gastos de API se introdujo un módulo unificado (`agent_core/utils/token_tracker.py`):
* **Captura Unificada:** Toda llamada al LLM pasa por este rastreador: Interacciones regulares en GUI/Telegram, llamadas a las herramientas del **AutoCoder** para programar, rutinas generativas en **Segundo Plano** e incluso Transcripciones de **Audio**.
* **Persistencia:** Mantiene un registro exacto (Timestamp, Texto origen truncado, Input/Output Tokens, Costo en USD y Familia del Modelo utilizado) dentro de `agent_core/memoria/usage_history.json`.
* **Costo Dinámico:** Interpreta el prefijo de la familia del modelo (`pro`, `flash`, `lite`) para asignar sus tablas de precios unitarios con alta fidelidad.
* **Dashboard FrontEnd:** Se añadió el módulo global `/usage` a la plataforma web Angular. Esta tabla visualiza de forma elegante todas las interacciones previas junto a tarjetas interactivas que denotan el costo total y consumos globales. 

## 6. Sistema de Gestión de Tareas (Scheduler)
Se implementó un organizador de tiempo y rutinas totalmente asíncrono utilizando `APScheduler`. Permite al agente programar tareas futuras.
* **Integración API-Frontend:** Exposición de las tareas (almacenadas en `agent_core/memoria/episodica/recordatorios.json`) a través de la API REST (`GET`, `POST`, `DELETE /api/tasks`).
* **UI en Angular:** Sección dedicada (`app-tasks`) donde el usuario gestiona visualmente **Recordatorios (fecha exacta)** y **Rutinas Dinámicas (intervalos)**, sin necesidad de usar prompts por el chat. Al crear o eliminar tareas aquí, el sistema inyecta/cancela callbacks en el scheduler global asíncrono.

---

## 7. Estructura de Archivos Clave
- `agent_core/main.py`: Cerebro orquestador y compilador de grafos.
- `agent_core/mcp_client.py`: Enlace asíncrono robusto con herramientas externas.
- `agent_core/telegram_bot.py`: Gateway de comunicación con Telegram y webhooks.
- `agent_core/api_endpoints.py`: Rutas FastAPI para conexión e integración de la Interfaz Web.
- `agent_core/scheduler_manager.py`: Motor local y asíncrono de recordatorios diarios.
- `agent_core/utils/token_tracker.py`: Útil universal para imputación de costos LLM.
- `agent_core/sub_agents/dev_agent.py`: Agente de auto-extensión (puede crear otros agentes).
- `leygo-gui/src/app/`: Estructura principal de la aplicación frontend con Angular.

## Próximos Pasos Sugeridos
* **Agentes de Larga Duración:** Implementar procesos que "duerman" y despierten con eventos externos (webhooks reales).
* **Consolidación de Identidad:** Refinar la personalidad de Leygo como un asistente omnicanal (Telegram, Chat, CLI).
* **Multi-modalidad:** Expandir el procesamiento de audio actual a procesamiento de imágenes nativo por sub-agentes.
