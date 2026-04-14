import os
from typing import List, Callable
from .base import BaseSubAgent

class AssistantAgent(BaseSubAgent):
    @property
    def model(self) -> str:
        return os.environ.get("MODEL_ASSISTANT")

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

⚠️ REGLA CRÍTICA sobre chat_id: Cuando uses herramientas de schedulers/recordatorios, el parámetro `chat_id` DEBE ser EXACTAMENTE el valor de `thread_id` mostrado arriba (es un ID numérico de Telegram). NUNCA uses el nombre del usuario (ej. "Jesus") como chat_id. Si el thread_id es "default_session", usa "default_session" tal cual.

Manejas la agenda, los emails y las rutinas guardadas del usuario. Tienes acceso completo a usar Schedulers locales o interactuar con las APIs de Google.

⚠️ REGLA ANTI-ALUCINACIÓN: NUNCA confirmes que has creado un recordatorio, agendado un evento o enviado un correo a menos que hayas utilizado la HERRAMIENTA ("tool") correspondiente con éxito y recibido confirmación. Si el usuario te pide enviarlo por una plataforma donde no tienes permisos (como enviar chat a "TI" cuando falla la API de chat), DEBES informarle que no puedes completarlo por falta de permisos en vez de decir "ya lo envié".

MEMORIA EPISÓDICA DEL USUARIO:
{episodic_context}
"""

    def get_tools(self, all_available_tools: list) -> List[Callable]:
        names = [
            "crear_recordatorio_solo_texto_para_usuario", "listar_tareas_programadas", 
            "crear_rutina_texto_periodica_para_usuario", "eliminar_tarea_programada",
            "agendar_accion_autonoma_agente", "agendar_rutina_autonoma_agente",
            "leer_correos_recientes", "modificar_etiquetas_correo", "enviar_correo", "listar_eventos_calendario", 
            "responder_evento_calendario", "crear_evento_calendario", "leer_hoja_calculo", "escribir_hoja_calculo", 
            "listar_espacios_chat", "leer_mensajes_chat", "enviar_mensaje_chat", "buscar_chat_directo"
        ]
        return [t for t in all_available_tools if getattr(t, "name", None) in names]
