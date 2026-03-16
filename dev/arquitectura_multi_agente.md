# Arquitectura Multi-Agente: Patrón Supervisor-Worker

Esta propuesta conceptual ha sido levantada a petición del usuario para expandir las capacidades del "Self-Extending Agent" usando el patrón **Agent-to-Agent**.

Dado que este proyecto está construido fuertemente sobre **LangGraph**, implementar una red de múltiples agentes orquestados por un Agente Principal no solo es posible, sino que es el estándar actual (SOTA - State of the Art) recomendado por Google y LangChain.

## El Concepto 'Agent-to-Agent'

Actualmente, nuestro agente es **"Monolítico"**, es decir, tiene un único modelo LLM (Gemini) expuesto a muchísimas herramientas en un solo grafo.
El enfoque Agent-to-Agent divide esto en una arquitectura **"Jerárquica" o "De Enjambre"**.

### Rol del Agente Principal (Orquestador / Supervisor)
En lugar de que el Agente Principal haga el trabajo (como descargar un Excel, armar código, agendar Google Calendar, todo mezclado), su System Prompt se modificará para actuar únicamente como un **Manager / Router**.
- **Input:** Recibe el pedido del Humano vía Telegram.
- **Acción:** Piensa *"¿Esto requiere investigación? ¿Codificación? ¿Asistente de finanzas?"* y **delega** la tarea invocando el Grafo (o la Tool Sub-grafada) de un Sub-Agente especializado.
- **Output:** Recibe la respuesta consolidada del Sub-Agente y se la cuenta al Humano.

### Los Sub-Agentes (Workers)
Serán instancias separadas de LangChain o pequeños grafos independientes orientados a propósitos de nicho.
- **Agente "Dev" (Auto-Coder):** Solo tiene el System Prompt centrado en código, tiene acceso total a E2B, MCP Github y las herramientas de guardado.
- **Agente "Secretary" (Asistente de Google Workspace):** Solo sabe de la API de Gmail, Google Calendar e intríngulis de Sheets.
- **Agente "Investigator":** Solo tiene herramientas de Web Search y un System Prompt instruido a ser exhaustivo.

## ¿Cómo se conecta técnicamente en LangGraph?
En la evolución de nuestro código, lograrlo implicaría los siguientes pasos técnicos en `agent_core`:

1.  **Multiple Sub-graphs:** En LangGraph, un nodo de un grafo general puede ser en sí mismo "otro grafo". Se compilarán varios objetos `StateGraph`.
2.  **State Management Compartido / Aislado:** El Supervisor envía al sub-agente un sub-conjunto de `messages`. El sub-agente hace su loop `agent -> tools -> agent`, llega a su propio nodo `END`, y devuelve la respuesta al grafo Superior.
3.  **Handoffs (Traspasos):** Se usan mecanismos donde el Output del Agente 1 (Ej: "Investigué esta API, aquí está el JSON") se pasa como Input directo al Agente 2 ("Codifica un script con base en este JSON de la API").

## Beneficios de este diseño (Pros):
*   **Ahorro Brutal de Tokens:** El Supervisor no arrastrará la "basura y logs largos" de la consola del Programador en sus prompts generales.
*   **Menos Confusión del LLM:** Disminuyen los errores donde el Agente confunde una herramienta de código con una de agenda. Prompts hiper-especializados siempre rinden mejor que un Prompt monolítico kilométrico.
*   **Extensibilidad Infinita:** Si mañana necesitas que el agente opere Crypto, creas un "Sub-Agente Trader" y el Supervisor simplemente se entera de que ahora puede "pedirle cosas" al Trader.

## Próximos Pasos (Hoja de Ruta):
Cuando decidas implementar esta Fase, el primer paso será refactorizar `agent_core/main.py`.
Separaremos las herramients MCP en un grafo "Coder", las de Web y Calendar en un grafo "Assistant", y el principal será solo el `SupervisorNode`.
