from typing import List, Callable
from ..base import BaseSubAgent

class OscarAgent(BaseSubAgent):
    @property
    def model(self): return "gemini-3-flash-preview"
    @property
    def name(self): return "oscar"
    @property
    def description(self): return "Senior Developer experto en Code Review y gestion de GitHub (Oscar)."
    @property
    def system_prompt(self): return "Eres Oscar, un Senior Developer con años de experiencia en revision de codigo, arquitectura de software y mejores practicas. Tu objetivo es realizar code reviews exhaustivos, identificar bugs, proponer mejoras de rendimiento y legibilidad, y gestionar issues en GitHub de manera profesional."
    
    def get_tools(self, all_available_tools):
        # Oscar necesita herramientas de GitHub y busqueda en internet
        github_tools = [
            "get_file_contents", "list_pull_requests", "get_pull_request", 
            "get_pull_request_files", "create_issue", "add_issue_comment",
            "update_issue", "list_issues", "search_issues", "create_pull_request_review",
            "buscar_en_internet"
        ]
        return [t for t in all_available_tools if getattr(t, "name", None) in github_tools]
