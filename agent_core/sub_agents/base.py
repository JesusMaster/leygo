from typing import List, Callable
from pydantic import BaseModel

class BaseSubAgent:
    """
    Interface base que todo sub-agente debe implementar para ser descubierto y orquestado 
    """
    
    def __init__(self):
        self.load_env()
        pass
        
    def load_env(self):
        """Carga automáticamente las variables de entorno de un archivo .env en la misma carpeta que el agente."""
        import inspect
        import os
        from dotenv import load_dotenv
        
        # Obtener el archivo donde está definida la subclase actual
        module = inspect.getmodule(self.__class__)
        if module and hasattr(module, '__file__'):
            env_path = os.path.join(os.path.dirname(os.path.abspath(module.__file__)), '.env')
            if os.path.exists(env_path):
                load_dotenv(env_path, override=True)

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
        """El prompt especializado que dictará el comportamiento de este sub-agente.
        Por defecto, intenta cargar y combinar 'memoria_episodica.md' y 'memoria_procedimental.md'.
        """
        import inspect
        import os
        
        module = inspect.getmodule(self.__class__)
        if not module or not hasattr(module, '__file__'):
            return f"Ere el agente {self.name}. Haz tu trabajo lo mejor que puedas."
            
        base_dir = os.path.dirname(os.path.abspath(module.__file__))
        episodic_path = os.path.join(base_dir, "memoria", "memoria_episodica.md")
        procedural_path = os.path.join(base_dir, "memoria", "memoria_procedimental.md")
        prefs_path = os.path.join(base_dir, "memoria", "usuarios_preferencias.md")
        
        prompt_parts = []
        
        if os.path.exists(procedural_path):
            with open(procedural_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    prompt_parts.append(f"--- MEMORIA PROCEDIMENTAL (Instrucciones de cómo actuar) ---\n{content}")
                    
        if os.path.exists(episodic_path):
            with open(episodic_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    prompt_parts.append(f"--- MEMORIA EPISÓDICA (Contexto o Eventos Previos) ---\n{content}")

        if os.path.exists(prefs_path):
            with open(prefs_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    prompt_parts.append(f"--- PREFERENCIAS DEL USUARIO ---\n{content}")
                    
        if prompt_parts:
            # Inject identity
            intro = f"Eres el agente especializado: {self.name}.\nDescripción: {self.description}\n\n"
            return intro + "\n\n".join(prompt_parts)
            
        raise NotImplementedError("Debes sobrescribir system_prompt o proveer archivos de memoria .md")
        
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
