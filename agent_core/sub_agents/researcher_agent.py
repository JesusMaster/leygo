import os
from typing import List, Callable
from .base import BaseSubAgent

class ResearcherAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "researcher"
        
    @property
    def description(self) -> str:
        return "ÚLTIMO RECURSO / PRIORIDAD BAJA. Úsalo para buscar en internet (web) SÓLO cuando estés completamente seguro de que el Agente MCP (bases de datos/herramientas internas de la empresa) no tiene la información."
        
    @property
    def system_prompt(self) -> str:
        return """Eres el Researcher Agent.
La fecha actual es: {current_time_iso}.
Tu deber es buscar exhaustivamente información en internet, leer páginas web y estructurarla con exactitud para responder la duda del usuario o del Supervisor.
"""

    def get_tools(self, all_available_tools: list) -> List[Callable]:
        names = ["buscar_en_internet"]
        return [t for t in all_available_tools if getattr(t, "name", None) in names]
