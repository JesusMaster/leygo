import os
from typing import List, Callable
from .base import BaseSubAgent

class McpAgent(BaseSubAgent):
    """Sub-agente dedicado a usar todas las herramientas de los servidores MCP configurados.
    
    Cuando se añade un nuevo servidor en mcp_config.yaml, sus herramientas están 
    automáticamente disponibles para este agente en el próximo reinicio.
    """

    def __init__(self):
        self._mcp_tools = []
        self._tools_text = ""
        self._tools_names = []

    def set_tools(self, all_available_tools: list):
        # Herramientas locales a excluir (nombres en español o prefijos conocidos)
        local_tool_names = {
            "crear_y_ejecutar_herramienta_local", "usar_herramienta_local", "administrar_memoria_episodica",
            "escribir_archivo_en_proyecto", "eliminar_archivo_en_proyecto", "buscar_en_internet", 
            "crear_recordatorio_solo_texto_para_usuario", "listar_tareas_programadas",
            "crear_rutina_texto_periodica_para_usuario", "eliminar_tarea_programada",
            "agendar_accion_autonoma_agente", "agendar_rutina_autonoma_agente",
            "leer_correos_recientes", "modificar_etiquetas_correo", "enviar_correo", "listar_eventos_calendario", "responder_evento_calendario",
            "crear_evento_calendario", "leer_hoja_calculo", "escribir_hoja_calculo", "listar_espacios_chat",
            "leer_mensajes_chat", "enviar_mensaje_chat", "buscar_chat_directo",
        }

        # Separar solo las herramientas que son de MCP (las que no están en la lista local)
        self._mcp_tools = [
            t for t in all_available_tools
            if getattr(t, "name", t.__name__ if hasattr(t, "__name__") else str(t)) not in local_tool_names
        ]

        # Generar texto de las herramientas y sus nombres
        lines = []
        names = []
        for t in self._mcp_tools:
            name = getattr(t, "name", "unknown")
            desc = getattr(t, "description", "")
            # Limpiar descripciones muy largas
            desc = desc.split('\\n')[0][:100] + "..." if len(desc) > 100 else desc
            lines.append(f"- **{name}**: {desc}")
            names.append(name)
            
        self._tools_names = names
        self._tools_text = "\\n".join(lines)

    @property
    def name(self) -> str:
        return "mcp"

    @property
    def description(self) -> str:
        if not self._tools_names:
            return "Para tareas que involucren herramientas externas de MCP configuradas."
            
        return (
            "CEREBRO DE NEGOCIO Y REPOSITORIOS (MCP). Contiene integraciones externas"
            f"Tiene {len(self._tools_names)} herramientas MCP disponibles."
        )

    @property
    def system_prompt(self) -> str:
        return f"""Eres el MCP Agent, especialista en usar servicios externos conectados a través del Model Context Protocol (MCP).
La fecha actual es: {{current_time_iso}}.

**ACTUALMENTE ESTÁS CONECTADO A LAS SIGUIENTES HERRAMIENTAS MÚLTIPLES:**
{self._tools_text}

## REGLAS DE USO VITALES:
1. SIEMPRE usa las herramientas directamente. NUNCA inventes ni asumas lo que la herramienta devolverá.
2. Si te hacen preguntas vagas o específicas de una herramienta en particular, evalúa EXACTAMENTE cuál herramienta de tu lista resuelve eso.
3. Cuidado con el contexto: por defecto, las URLs y repositorios se basan en la herramienta específica (ej: GitHub para repositorios y código de desarrollador). Si la pregunta es sobre "qué es X proyecto", busca la herramienta más apropiada para ello de las que se te listaron arriba.
4. Si usas una herramienta y te devuelve un error (ej. 404 Not Found o Invalid Argument), significa que esa data no existe con los parámetros que ingresaste. No inventes que tuvo éxito. Usa otra herramienta si es necesario, corrige los argumentos o explícale al usuario.
5. Responde siempre detallando el contenido exacto y real obtenido de las herramientas. NO asumas datos.

MEMORIA EPISÓDICA:
{{episodic_context}}
"""

    def get_tools(self, all_available_tools: list) -> List[Callable]:
        """Devuelve EXCLUSIVAMENTE las herramientas MCP (las que NO son locales)."""
        if not self._mcp_tools:
            self.set_tools(all_available_tools)
        return self._mcp_tools
