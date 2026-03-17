# Resumen de Proyecto: Leygo Agent (Self-Extending Agent con LangGraph y MCP)

Este documento sintetiza la arquitectura, los componentes clave y, sobre todo, **los aprendizajes críticos y soluciones de errores** del desarrollo de **Leygo**, un asistente de IA autónomo basado en LangGraph y el Model Context Protocol (MCP).

## 1. Arquitectura General: Sistema Multi-Agente Jerárquico
El proyecto ha evolucionado de un agente monolítico a una red de agentes especializados orquestados por LangGraph:
- **Supervisor Principal:** Actúa como el Director de Orquesta. Analiza el input (texto o voz) y decide a qué sub-agente delegar la tarea basándose en su descripción y capacidades.
- **Sub-Agentes Especializados (Discovery & Hot-Reload):** Leygo descubre automáticamente nuevos agentes en `agent_core/sub_agents/`. Soporta carga en caliente (hot-reload), permitiendo que el Supervisor aprenda nuevas habilidades o cambie su estructura sin reiniciar el sistema.
- **BaseSubAgent:** Interfaz común que estandariza la comunicación, el filtrado de herramientas y la selección de modelo (default: **gemini-3.1-flash-lite-preview**).

## 2. Dockerización y Servicios
Para garantizar consistencia y facilitar el despliegue, el sistema está completamente contenedorizado:
- **leygo-bot:** Servicio FastAPI + `python-telegram-bot` que gestiona la interfaz web y móvil.
- **leygo-cli:** Interfaz de terminal interactiva para desarrollo y debugging.
- **Persistencia:** Volúmenes de Docker vinculan las carpetas de `memoria/` y `sub_agents/`, permitiendo que el aprendizaje y los nuevos scripts sobrevivan al reinicio de los contenedores.

## 3. Interfaz de Voz Nativa (Voz-a-Comando)
Una de las innovaciones clave es la integración de audio fluida en Telegram:
- **Flujo:** El bot detecta una nota de voz -> La descarga -> Gemini 3.1 Flash Lite la transcribe de forma literal casi instantánea -> El texto resultante se inyecta directamente como input al sistema.
- **Resultado:** El usuario puede "hablarle" a Leygo. Leygo "escucha", entiende el comando y responde ejecutando las herramientas necesarias, eliminando la fricción de escribir.

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

---

## 5. Estructura de Archivos Clave
- `agent_core/main.py`: Cerebro orquestador y compilador de grafos.
- `agent_core/mcp_client.py`: Enlace asíncrono robusto con herramientas externas.
- `agent_core/telegram_bot.py`: Gateway de comunicación con Telegram y lógica de audio.
- `agent_core/sub_agents/dev_agent.py`: Agente de auto-extensión (puede crear otros agentes).
- `agent_core/utils/audio_utils.py`: Motor de transcripción rápida vía Gemini.

## Próximos Pasos Sugeridos
* **Agentes de Larga Duración:** Implementar procesos que "duerman" y despierten con eventos externos (webhooks reales).
* **Consolidación de Identidad:** Refinar la personalidad de Leygo como un asistente omnicanal (Telegram, Chat, CLI).
* **Multi-modalidad:** Expandir el procesamiento de audio actual a procesamiento de imágenes nativo por sub-agentes.
