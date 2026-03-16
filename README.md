# Leygo 🤖

Un asistente de Inteligencia Artificial personal, autónomo y **auto-extensible**, diseñado para integrarse profundamente con tu flujo de trabajo diario. Este proyecto actúa como un "Cerebro Central" jerárquico capaz de interactuar con múltiples plataformas, aprender de sus errores, y **programar sus propios sub-agentes especializados** on-the-fly.

## ✨ Características Principales

*   **Arquitectura Multi-Agente Jerárquica (LangGraph):**
    *   **Supervisor Central:** Orquestador inteligente que delega tareas a sub-agentes especializados.
    *   **Auto-Discovery & Hot-Reload:** El sistema detecta nuevos sub-agentes en la carpeta `sub_agents/` y recompila el grafo en tiempo real sin reiniciar el proceso.
*   **Integración con Google Workspace:**
    *   **Gmail, Calendar, Sheets y Google Chat:** Gestión completa de correos, eventos, datos y comunicación bidireccional.
*   **Sistema de Memoria Segmentada:**
    *   **Memoria Episódica:** Contexto de usuario, preferencias e identidad (archivos `.md`). Segmentada en **Memoria Global** (`agent_core/memoria/`) e **Individual** por agente.
    *   **Memoria Procedimental:** Catálogo de herramientas técnicas, parámetros y guías de ejecución autogeneradas.
*   **Auto-Coder & Auto-Extension:**
    *   El **Dev Agent** tiene la capacidad de crear, probar y desplegar nuevos sub-agentes y herramientas en Python para resolver tareas complejas.
*   **Soporte MCP (Model Context Protocol):**
    *   Conectividad con servidores externos (GitHub, Postgres, Slack, etc.) mediante Handshake dinámico definido en `mcp_config.yaml`.

## 🚀 Arquitectura del Proyecto

```text
self-agent/
├── agent_core/
│   ├── main.py                 # Orquestador, Supervisor y Lógica de Hot-Reload
│   ├── mcp_client.py           # Gestor de conexiones MCP (Model Context Protocol)
│   ├── memory_utils.py         # Motor de gestión de Memorias (Episódica/Procedimental)
│   ├── auto_coder.py           # Sandbox de ejecución y creación de herramientas
│   ├── google_tools.py         # Integración nativa con Google Workspace
│   └── sub_agents/             # 🧠 El corazón dinámico del sistema (Swarm)
│       ├── base.py             # Clase base para todos los agentes
│       ├── dev/                # Dev Agent (Programador Principal)
│       ├── mcp/                # Mcp Agent (Especialista en herramientas externas)
│       └── researcher/         # Researcher Agent (Búsqueda y análisis Web)
├── agent_core/memoria/         # 📁 Almacenamiento persistente de aprendizaje
└── README.md
```

## 🧠 Ciclo de Vida del Agente

1.  **Handshake:** Inicializa conexiones con servidores MCP (locales o remotos SSE).
2.  **Discovery:** Escanea `sub_agents/` y carga dinámicamente las clases que heredan de `BaseSubAgent`.
3.  **Context Injection:** Inyecta las preferencias del usuario (`usuario_preferencias.md`) y las lecciones aprendidas en los prompts de sistema.
4.  **Ejecución & Extensión:** Ante una tarea nueva, el sistema puede decidir si utiliza una herramienta existente o si el **Dev Agent** debe programar una nueva solución.

## 🛠 Instalación y Configuración

1.  **Clonar repositorio e instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configurar `.env` en `agent_core/`:**
    ```env
    GOOGLE_API_KEY="tu_api_key_gemini"
    TELEGRAM_TOKEN="tu_token_bot"
    ```
3.  **Ejecución:**
    ```bash
    # Modo interactivo (CLI)
    python agent_core/main.py
    
    # Modo Bot (Telegram/Webhooks)
    python agent_core/telegram_bot.py
    ```

## 🤝 Protocolo MCP
Puedes expandir las capacidades de **Leygo** añadiendo servidores en `agent_core/mcp_config.yaml`. Soporta transporte `stdio` (scripts locales) y `sse` (servidores remotos).

---
*Hecho para potenciar la productividad mediante flujos de trabajo autónomos y auto-evolutivos.*
