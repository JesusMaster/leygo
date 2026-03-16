from typing import List, Callable
from .base import BaseSubAgent

class AssistantAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "assistant"
        
    @property
    def description(self) -> str:
        return "Gestión de correos, bandeja de entrada, invitaciones a Google Calendar, Sheets, Chats directos, o agregar/cancelar Recordatorios Locales y alarmas iterativas."
        
    @property
    def system_prompt(self) -> str:
        return """Eres el Assistant Agent ("Workspace & Schedulers").
La fecha actual es: {current_time_iso}. Tu `thread_id` (para schedulers) es: {thread_id}.
Manejas la agenda, los emails y las rutinas guardadas del usuario. Tienes acceso completo a usar Schedulers locales o interactuar con las APIs de Google.

MEMORIA EPISÓDICA DEL USUARIO:
{episodic_context}
"""

    def get_tools(self, all_available_tools: list) -> List[Callable]:
        names = [
            "programar_recordatorio", "listar_recordatorios", "programar_intervalo_dinamico", "eliminar_recordatorio",
            "leer_correos_recientes", "modificar_etiquetas_correo", "enviar_correo", "listar_eventos_calendario", 
            "responder_evento_calendario", "crear_evento_calendario", "leer_hoja_calculo", "escribir_hoja_calculo", 
            "listar_espacios_chat", "leer_mensajes_chat", "enviar_mensaje_chat", "buscar_chat_directo"
        ]
        return [t for t in all_available_tools if getattr(t, "name", None) in names]
