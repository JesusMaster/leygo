# Leygo 🤖

Un asistente de Inteligencia Artificial personal, autónomo y **auto-extensible**, diseñado para integrarse profundamente con tu flujo de trabajo diario. Este proyecto actúa como un "Cerebro Central" jerárquico capaz de interactuar con múltiples plataformas, ejecutar tareas recurrentes, aprender de sus interacciones y **programar sus propios sub-agentes especializados** en tiempo real.

---

## ✨ Características Principales

### 🧠 Arquitectura Multi-Agente Jerárquica (LangGraph)
*   **Supervisor Central:** Orquestador inteligente que evalúa el historial completo y delega tareas a sub-agentes especializados mediante la herramienta estructurada `Route`. Soporta *Zero-Shot Handoff* entre agentes para tareas multipaso complejas.
*   **Auto-Discovery & Hot-Reload:** El sistema detecta nuevos sub-agentes en la carpeta `sub_agents/` y recompila el grafo de LangGraph dinámicamente sin reiniciar el contenedor.
*   **Gestión Estricta de Herramientas:** Restricciones sistémicas preventivas de loops infinitos, forzando delegaciones limpias e impidiendo el *"tool hallucination"*.

### ⚡ Streaming en Tiempo Real (SSE)
*   **Server-Sent Events:** Transmisión de respuestas token por token (`astream_events`), brindando retroalimentación visual fluida e inmediata en la interfaz web.
*   **Seguimiento de Orquestación:** Inspección profunda del grafo de LangGraph para clasificar eventos (`status`, `token`, `done`, `error`) y notificar al frontend qué agente exacto está trabajando en cada paso.
*   **Fallback Integrado:** Si el Supervisor Central decide resolver la consulta directamente sin delegar, el sistema captura y transmite la respuesta íntegra sin fallos de streaming.

### 💰 Gestión de Costos y Tokens Granular
*   **Token Tracker Acumulativo:** Contabilidad precisa del uso total de tokens y cálculo automático de costos en dólares por cada interacción. Toda llamada al LLM por parte de cualquier sub-agente se consolida en la respuesta final.
*   **Historial de Presupuesto:** Registro metódico guardado localmente en `usage_history.json` para auditoría y futuras alertas proactivas.

### ⏰ Ejecución Autónoma y Schedulers (APScheduler)
*   **Recordatorios y Rutinas:** Capacidad de agendar recordatorios simples por texto o rutinas dinámicas generativas (cron, intervalos o fechas específicas). Configurado rígidamente en la zona horaria garantizada (ej. `America/Santiago`).
*   **Acciones de Agente en Diferido:** El usuario puede pedirle a Leygo agendar *comportamientos de agente* para el futuro. APScheduler gatilla la inyección de contexto a su hora en background.

### 🔌 Integración con Google Workspace
*   **Gmail, Calendar, Sheets y Docs:** Interacción y lectura dentro del ecosistema de Google mediante autenticación local (`credentials.json`), permitiendo gestionar el día a día.

### 💾 Sistema de Memoria Segmentada
*   **Memoria Episódica:** Contextos conversacionales (memoria a corto plazo) y preferencias crónicas del usuario que acompañan al prompt del sistema.
*   **Memoria Procedimental:** Catálogo histórico de lecciones técnicas (`lecciones_aprendidas.md`), errores solucionados recurrentes y guías operativas.

### 💻 Auto-Coder & Auto-Extension
*   El **Dev Agent** tiene la capacidad de crear código, probarlo localmente, y desplegar herramientas o scripts nuevos en Python/Node que amplíen las capacidades de Leygo de manera permanente.

### 🔗 Soporte MCP (Model Context Protocol)
*   **MCP Agent:** Conectividad estandarizada con múltiples dependencias externas como Repositorios Locales (GitHub), bases de datos, APIs de información, etc., a través de archivos preconfigurados dinámicamente (`mcp_config.yaml`).

---

## 🚀 Arquitectura del Proyecto

```text
self-agent/
├── agent_core/
│   ├── main.py                 # Orquestador: Supervisor LangGraph, Routing y Streaming
│   ├── scheduler_manager.py    # Motor de APScheduler para tareas futuras
│   ├── mcp_client.py           # Cliente Model Context Protocol
│   ├── utils/                  # Herramientas utilitarias (ej. Token Tracker, Auth)
│   ├── keys/                   # Credenciales de Google y Base de Datos local
│   ├── auto_coder.py           # Sandbox de ejecución y auto-programación (Dev)
│   ├── telegram_bot.py         # Webhook o Polling bot para interactuar remotamente
│   ├── api_endpoints.py        # API REST para el Frontend (FastAPI) con control SSE
│   └── sub_agents/             # 🧠 Sub-Agentes Independientes
│       ├── base.py             # Interfaces Base
│       ├── dev_agent.py        # Dev Agent (Ingeniero de Software y Sistemas)
│       ├── assistant_agent.py  # Assistant Agent (Agenda y Google Workspace)
│       ├── mcp_agent.py        # Mcp Agent (Interacción con múltiples servidores MCP)
│       └── research_agent.py   # Research Agent (Búsquedas e investigación en red)
├── agent_core/memoria/         # 📁 JSONs y MDs (Episódica, Procedimental, Presupuestos)
├── dev/                        # Reportes y logs de desarrollo
├── leygo-gui/                  # 💻 Frontend Web en Angular (SSE Client, Markdown parcer)
└── docker-compose.yml          # Orquestación de infraestructura (Containers FastAPI + Nginx)
```

---

## ⚙️ Instalación y Despliegue (Docker)

La arquitectura de Leygo funciona eficientemente dentro de comandos dockerizados para aislar las dependencias de Python del CLI y estandarizar la conectividad red (Nginx para el front).

1.  **Clonar repositorio y preparar variables:**
    Crea un archivo `.env` en `agent_core/.env`:
    ```env
    GOOGLE_API_KEY="tu_api_key_gemini"
    TELEGRAM_TOKEN="tu_token_bot"
    TELEGRAM_CHAT_ID="tu_id_numerico_principal"
    MODEL_SUPERVISOR="gemini-2.5-pro"
    TZ="America/Santiago"
    ```

2.  **Construir e iniciar contenedores:**
    ```bash
    docker-compose up -d --build
    ```

3.  **Monitoreo del Agente:**
    Sigue el comportamiento interno del sistema, la delegación de agentes y el streaming con:
    ```bash
    docker logs -f leygo-bot
    ```

---

*Hecho por @JesusMaster para redefinir el estándar de agentes IA productivos en entornos cerrados.*
