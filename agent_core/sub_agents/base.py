from typing import List, Callable
from pydantic import BaseModel

class BaseSubAgent:
    """
    Interface base que todo sub-agente debe implementar para ser descubierto y orquestado 
    automáticamente por el Agente Supervisor (main.py).
    """
    
    @property
    def name(self) -> str:
        """Nombre interno del agente (ej. 'dev', 'fitness')."""
        raise NotImplementedError
        
    @property
    def model(self) -> str:
        """(Opcional) Modelo específico LLM a usar para este agente (ej. 'gemini-2.5-flash'). Si retorna None, usa el default."""
        return None
        
    @property
    def description(self) -> str:
        """Descripción concisa para que el Supervisor sepa QUÉ tareas delegarle."""
        raise NotImplementedError
        
    @property
    def system_prompt(self) -> str:
        """El prompt especializado que dictará el comportamiento de este sub-agente."""
        raise NotImplementedError
        
    def get_tools(self, all_available_tools: list) -> List[Callable]:
        """
        Retorna la lista de herramientas específicas a las que este agente en particular 
        tiene permitido acceder.
        Recibe todas las herramientas cargadas en inicialización (MCP + fallback) como ayuda.
        """
        return []

    def set_tools(self, all_available_tools: list):
        """
        Método opcional para que el agente reciba las herramientas antes de la compilación
        del grafo (útil para generar descripciones dinámicas basadas en herramientas).
        """
        pass
