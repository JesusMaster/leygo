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

### H.bis Loops Infinitos en AutoCoder y Workers
* **Problema:** El `dev_agent` (vía `auto_coder.py`) podía quedar atrapado en un ciclo infinito de reintentos al generar código con errores. Cada reintento perdía contexto ("amnesia") y comenzaba desde cero, sin saber qué error corregir.
* **Solución Dual:**
  1. **Memoria de Chat en Reintentos:** Se modificó `crear_y_ejecutar_herramienta_local` para mantener el historial completo de la conversación entre reintentos, permitiendo al LLM recordar el error original y corregirlo.
  2. **Instrucción Anti-Loop en Workers:** Se agregó una directiva crítica al System Prompt de todos los sub-agentes: si una herramienta falla repetidamente, deben detenerse, reportar el error al Supervisor y terminar su turno en lugar de reintentar indefinidamente.

### I. Cortocircuito de Orquestación (Zero-Shot Handoff Failure)
* **Problema:** En tareas multipaso (ej. "lee un archivo y luego manda correo"), el Supervisor delegaba al Agente MCP para leer... pero una vez que el MCP leía, el Supervisor cortaba el flujo asumiendo que el usuario ya estaba respondido, dejando el correo sin enviar.
* **Solución:** 
  1. Activación de Evaluación Continua: Se quitó el *short-circuit* manual que cortaba el grafo apenas el LLM respondía con texto. 
  2. Forzado Estricto de Sistema: Se configuró `tool_choice="any"` en el `bind_tools` del Supervisor, forzándolo a utilizar **siempre** la herramienta estructural `Route` (ya sea para seguir derivando iterativamente a otros sub-agentes, o usar `Route('FINISH')` para cerrar el ciclo limpiamente).

### J. Desfase Horario (Timezone Drift) en Scheduling (UTC vs Local)
* **Problema:** Tareas agendadas para "en 2 minutos" se ejecutaban con 3 horas de retraso. El contenedor en Docker opera en UTC. APScheduler estaba configurado para aislar el entorno en `America/Santiago`, pero el agente inyectaba objetos ingenuos (Naive Datetimes) creados con `datetime.now()`. APScheduler interpretaba malamente ese Naive Datetime UTC como si ya fuera Hora de Chile.
* **Solución:** Migración absoluta a Timezone-Aware Datetimes. Todo cálculo matemático temporal (`timedelta`) en `scheduler_manager.py` se genera inyectando forzosamente la zona horaria objetivo previa: `datetime.now(TIMEZONE)`.

### K. Errores de Auto-Descubrimiento en Generación Dinámica de Agentes
* **Problema:** El sub-agente `dev` creaba nuevos agentes instanciando las variables obligatorias (e.g., `self.name`) directamente dentro de `__init__()`. Esto causaba una caída (`property 'name' of 'NamiAgent' object has no setter`) durante el auto-descubrimiento al reconstruir el grafo, porque `BaseSubAgent` las define como `@property`. Además, la firma de `get_tools` carecía del argumento inyectado por el Supervisor (`all_available_tools`).
* **Solución:** Actualización estricta del `system_prompt` interno del `dev_agent` dictaminando reglas de sintaxis arquitectónica inmutables: obligatoriedad del uso de `@property` y firmas de métodos exactas para el correcto enlazado en `main.py`.

### L. TypeError en Contenido de Rutinas Generadas por LLM (`'list' object has no attribute 'strip'`)
* **Problema:** Al usar `gemini-2.5-flash-lite` (modelo liviano) para generar los mensajes de rutinas en `scheduler_manager.py`, la respuesta del LLM a través de LangChain retornaba `response.content` como una **lista de bloques** (`[{"text": "..."}]`) en lugar de un string plano. Al intentar llamar `.strip()` directamente sobre la lista, Python lanzaba el error `'list' object has no attribute 'strip'`.
* **Solución:** Verificación de tipo antes de extraer el texto: si `response.content` es una `list`, se itera y concatena el campo `"text"` de cada bloque con `"".join(...)`. Solo entonces se llama a `.strip()` sobre el string resultante.

### M. `next_run_time_iso` no se Actualizaba en Rutinas Recurrentes
* **Problema:** Las rutinas de tipo `interval` se ejecutaban correctamente, pero el archivo `recordatorios.json` nunca actualizaba el campo `next_run_time_iso` tras cada ejecución. Esto dejaba el JSON desincronizado (con fechas del pasado), causando inconsistencias visuales en la GUI y confusión al reiniciar el contenedor.
* **Causa:** La función `guardar_estado_jobs()` solo se invocaba al crear o eliminar tareas manualmente, nunca después de una ejecución automática de APScheduler.
* **Solución:** Registro de un **Listener de Eventos APScheduler** (`EVENT_JOB_EXECUTED`) al inicializar el scheduler global. Cada vez que una tarea se ejecuta exitosamente, el listener llama automáticamente a `guardar_estado_jobs()`, manteniendo el JSON siempre sincronizado con el tiempo real de la próxima ejecución.


## 5. Control de Costos y Uso de Tokens (Token Tracker)
Para habilitar una visibilidad completa de los gastos de API se introdujo un módulo unificado (`agent_core/utils/token_tracker.py`):
* **Captura Unificada:** Toda llamada al LLM pasa por este rastreador: Interacciones regulares en GUI/Telegram, llamadas a las herramientas del **AutoCoder** para programar, rutinas generativas en **Segundo Plano** e incluso Transcripciones de **Audio**.
* **Tracking Granular por Agente:** El sistema registra cada llamada de forma individual por sub-agente (`[supervisor]`, `[dev]`, `[mcp]`, `[researcher]`, etc.), permitiendo identificar con exactitud cuánto consume cada componente del sistema multi-agente.
* **Persistencia:** Mantiene un registro exacto (Timestamp, Texto origen truncado, Input/Output Tokens, Costo en USD y Familia del Modelo utilizado) dentro de `agent_core/memoria/usage_history.json`.
* **Costo Dinámico:** Interpreta el prefijo de la familia del modelo (`pro`, `flash`, `lite`) para asignar sus tablas de precios unitarios con alta fidelidad.
* **Dashboard FrontEnd:** Se añadió el módulo global `/usage` a la plataforma web Angular. Esta tabla visualiza de forma elegante todas las interacciones previas junto a tarjetas interactivas que denotan el gasto del mes actual, tokens y la barra de consumo contra el presupuesto.

### 5.1 Control de Presupuesto Mensual (Budget Limiter)
Se implementó un sistema de **cuota mensual en dólares** que protege contra gastos descontrolados:
* **Almacenamiento:** El límite se persiste como la variable `MONTHLY_BUDGET_USD` en el archivo `.env` del backend.
* **Cálculo en Tiempo Real:** La función `get_current_month_cost()` suma dinámicamente todos los registros del `usage_history.json` que pertenezcan al mes y año en curso.
* **Verificación Centralizada:** La función reutilizable `check_budget_exceeded()` en `token_tracker.py` encapsula toda la lógica de lectura del `.env` y comparación con el gasto acumulado, retornando un booleano y un mensaje de alerta.
* **Protección Transversal — 3 Puntos de Bloqueo:**
  1. **API GUI (`api_endpoints.py`):** El endpoint `/api/chat` intercepta las consultas antes de invocar al agente.
  2. **Telegram Bot (`telegram_bot.py`):** La función `handle_message_background` verifica la cuota antes de procesar cualquier mensaje entrante.
  3. **Tareas Programadas (`scheduler_manager.py`):** Tanto `send_dynamic_telegram_reminder` como `execute_agent_task` comprueban el presupuesto antes de consumir tokens, notificando al usuario por Telegram que la tarea fue pausada.
* **Edición desde el Frontend:** La vista de `/usage` en Angular permite visualizar la cuota actual, el porcentaje utilizado (barra de progreso) y editar el límite en línea. El cambio se persiste al backend vía el endpoint `/api/config`.

## 6. Sistema de Gestión de Tareas (Scheduler)
Se implementó un organizador de tiempo y rutinas totalmente asíncrono utilizando `APScheduler`. Permite al agente programar tareas futuras.
* **Integración API-Frontend:** Exposición de las tareas (almacenadas en `agent_core/memoria/episodica/recordatorios.json`) a través de la API REST (`GET`, `POST`, `DELETE /api/tasks`).
* **UI en Angular:** Sección dedicada (`app-tasks`) donde el usuario gestiona visualmente **Recordatorios (fecha exacta)** y **Rutinas Dinámicas (intervalos)**, sin necesidad de usar prompts por el chat. Al crear o eliminar tareas aquí, el sistema inyecta/cancela callbacks en el scheduler global asíncrono.
* **Respeto al Presupuesto:** Todas las tareas programadas verifican el presupuesto mensual antes de ejecutarse. Si la cuota fue superada, se envía una notificación al usuario y la ejecución se omite sin consumir tokens adicionales.
* **Sincronización Automática (Event Listener):** Un listener de `EVENT_JOB_EXECUTED` en APScheduler actualiza el archivo JSON automáticamente tras cada ejecución exitosa, manteniendo los tiempos de próxima ejecución (`next_run_time_iso`) siempre al día.
* **Modelo Liviano para Generación:** Los mensajes de rutinas generativos se producen con `gemini-2.5-flash-lite` (o el valor de `MODEL_SUPERVISOR`), evitando el uso de "reasoning tokens" ocultos que inflan los tokens de salida sin necesidad.

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
* **Alertas Proactivas de Presupuesto:** Enviar notificaciones al usuario cuando el gasto alcance el 80% y 90% del límite mensual configurado.
* **Límite por Consulta Individual:** Añadir un tope máximo de costo por consulta individual para prevenir operaciones excesivamente costosas.
* **Endurecimiento del Dev Agent:** Agregar validación automática post-generación (import check) para verificar que los agentes creados dinámicamente son importables antes de guardarlos.
