# Leygo 🤖

Un asistente de Inteligencia Artificial personal, autónomo y **auto-extensible**, diseñado para integrarse profundamente con tu flujo de trabajo diario. Este proyecto actúa como un "Cerebro Central" jerárquico capaz de interactuar con múltiples plataformas, ejecutar tareas recurrentes, aprender de sus interacciones y **programar sus propios sub-agentes especializados** en tiempo real.

---

## ✨ Características Principales

### 🧠 Arquitectura Multi-Agente Jerárquica (LangGraph)
*   **Supervisor Central:** Orquestador inteligente que evalúa el historial completo y delega tareas a sub-agentes especializados mediante la herramienta estructurada `Route`. Soporta *Zero-Shot Handoff* entre agentes para tareas multipaso complejas.
*   **Auto-Discovery & Hot-Reload:** El sistema detecta nuevos sub-agentes en la carpeta `sub_agents/` y recompila el grafo de LangGraph dinámicamente sin reiniciar el contenedor.
*   **Gestión Estricta de Alucinaciones:** Restricciones sistémicas a nivel `bind_tools` (`tool_choice="any"`) previniendo loops infinitos y forzando delegaciones limpias.

### ⏰ Ejecución Autónoma y Schedulers (APScheduler)
*   **Recordatorios y Rutinas:** Capacidad de agendar recordatorios simples por texto o rutinas dinámicas generativas (cron, intervalos o fechas específicas).
*   **Acciones de Agente en Diferido:** El usuario puede pedirle a Leygo agendar *comportamientos de agente* para el futuro (ej. *"revisa un archivo en 10 minutos y envíalo por correo"*). APScheduler gatilla la inyección de contexto en la hora exacta respetando la zona horaria local (`America/Santiago`).
*   **Persistencia Tolerante a Fallos:** Schedulers guardados y recuperados en almacenamiento episódico de formato JSON.

### 🔌 Integración con Google Workspace
*   **Gmail, Calendar, Sheets y Chat:** El `Assistant Agent` posee gestión íntegra de correos, invitaciones, calendarios y envío automáticos de reportes a espacios de Google Chat.

### 💾 Sistema de Memoria Segmentada
*   **Memoria Episódica:** Contextos conversacionales (memoria a corto plazo) y preferencias crónicas del usuario inyectados como base.
*   **Memoria Procedimental:** Catálogo histórico de lecciones técnicas, errores solucionados, herramientas y guías operativas.

### 💻 Auto-Coder & Auto-Extension
*   El **Dev Agent** tiene la capacidad de crear, probar localmente (`auto_coder.py`) y desplegar permanentemente nuevas herramientas o sub-agentes en Python dentro del propio ecosistema de Leygo.

### 🔗 Soporte MCP (Model Context Protocol)
*   **MCP Agent:** Conectividad robusta con repositorios locales, bases de datos (Postgres), y APIs de Slack o GitHub usando configuración dinámica YAML o Node.js.

---

## 🚀 Arquitectura del Proyecto

```text
self-agent/
├── agent_core/
│   ├── main.py                 # Orquestador: Supervisor LangGraph y Routing
│   ├── scheduler_manager.py    # Motor de APScheduler para tareas futuras
│   ├── mcp_client.py           # Cliente Model Context Protocol
│   ├── memory_utils.py         # Memoria Episódica y Procedimental
│   ├── auto_coder.py           # Sandbox de ejecución y auto-programación
│   ├── telegram_bot.py         # Recepción y webhook de Telegram
│   ├── api_endpoints.py        # API REST para el Frontend (FastAPI)
│   └── sub_agents/             # 🧠 Sub-Agentes Independientes
│       ├── base.py             # Interfaces Base
│       ├── dev/                # Dev Agent (Ingeniero de Software)
│       ├── assistant/          # Assistant Agent (Agenda y Google Workspace)
│       ├── mcp/                # Mcp Agent (Bases de datos y Repositorios)
│       └── researcher/         # Researcher Agent (Búsqueda Web Pública)
├── agent_core/memoria/         # 📁 JSONs y MDs de Estado del Agente
├── leygo-gui/                  # 💻 Frontend Web en Angular/Node
└── docker-compose.yml          # Despliegue en contenedores integrados
```

---

## ⚙️ Instalación y Despliegue (Docker)

La arquitectura de Leygo funciona eficientemente dentro de un entorno vectorizado en Docker para evitar colisiones de dependencias entre el Frontend GUI y los procesos Python en background.

1.  **Clonar repositorio y preparar variables de entorno:**
    Crea un archivo `.env` en `agent_core/.env`:
    ```env
    GOOGLE_API_KEY="tu_api_key_gemini"
    TELEGRAM_TOKEN="tu_token_bot"
    TELEGRAM_CHAT_ID="tu_id_numerico_principal"
    MODEL_SUPERVISOR="gemini-2.5-pro"
    ```

2.  **Construir e iniciar contenedores:**
    ```bash
    docker-compose up -d --build
    ```

3.  **Monitoreo del Agente:**
    Puedes seguir la orquestación (y ver cómo se transfieren tareas entre Supervisor y sub-agentes) examinando los logs de FastAPI:
    ```bash
    docker logs -f leygo-bot
    ```

---

*Hecho por @JesusMaster para redefinir el estándar de agentes IA productivos en entornos cerrados.*
