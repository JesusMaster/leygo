import os
from typing import List, Callable
from ..base import BaseSubAgent

def obtener_conversaciones_linkedin(limite: int = 5) -> str:
    """Obtiene los mensajes recientes de los chats de LinkedIn."""
    try:
        from linkedin_api import Linkedin
    except ImportError:
        return "Error: La librería 'linkedin-api' no está instalada. Pide al usuario que ejecute 'pip install linkedin-api'."
    
    username = os.getenv("LINKEDIN_USERNAME")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    if not username or not password:
        return "Error: Faltan LINKEDIN_USERNAME y/o LINKEDIN_PASSWORD en el archivo .env"
        
    try:
        api = Linkedin(username, password)
        conversaciones = api.get_conversations()
        
        if not conversaciones or 'elements' not in conversaciones:
            return "No se encontraron conversaciones o el formato de respuesta es inesperado."
            
        resultado = []
        for conv in conversaciones['elements'][:limite]:
            conv_id = conv.get('entityUrn', '').split(':')[-1]
            
            participantes = []
            for p in conv.get('participants', []):
                perfil = p.get('com.linkedin.voyager.messaging.MessagingMember', {}).get('miniProfile', {})
                nombre = f"{perfil.get('firstName', '')} {perfil.get('lastName', '')}".strip()
                if nombre:
                    participantes.append(nombre)
            
            eventos = conv.get('events', [])
            ultimo_mensaje = "Sin mensajes"
            if eventos:
                evento = eventos[0]
                contenido = evento.get('eventContent', {}).get('com.linkedin.voyager.messaging.event.MessageEvent', {})
                texto = contenido.get('customContent', {}).get('com.linkedin.voyager.messaging.event.message.TextContent', {}).get('text', '')
                if not texto:
                    texto = contenido.get('attributedBody', {}).get('text', 'Mensaje no textual o adjunto')
                ultimo_mensaje = texto
                
            resultado.append(f"ID Conversación: {conv_id} | Participantes: {', '.join(participantes)} | Último mensaje: {ultimo_mensaje}")
            
        return "\n".join(resultado)
    except Exception as e:
        return f"Error al conectar con LinkedIn: {str(e)}"

def enviar_mensaje_linkedin(destinatario_urn_id: str, mensaje: str) -> str:
    """Envía un mensaje a una conversación existente en LinkedIn usando su ID de Conversación."""
    try:
        from linkedin_api import Linkedin
    except ImportError:
        return "Error: La librería 'linkedin-api' no está instalada."
        
    username = os.getenv("LINKEDIN_USERNAME")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    if not username or not password:
        return "Error: Faltan LINKEDIN_USERNAME y/o LINKEDIN_PASSWORD en el archivo .env"
        
    try:
        api = Linkedin(username, password)
        api.send_message(message_body=mensaje, conversation_urn_id=destinatario_urn_id)
        return f"Mensaje enviado exitosamente a la conversación {destinatario_urn_id}."
    except Exception as e:
        return f"Error al enviar mensaje: {str(e)}"

class LinkedinAgent(BaseSubAgent):
    @property
    def model(self): 
        return "gemini-3.1-flash-lite-preview"
        
    @property
    def name(self): 
        return "linkedin"
        
    @property
    def description(self): 
        return "Agente para leer y enviar mensajes en los chats de LinkedIn."
        
    @property
    def system_prompt(self): 
        return "Eres el Linkedin Agent. Tu objetivo es gestionar los mensajes de LinkedIn del usuario. Puedes leer conversaciones recientes y enviar mensajes a chats existentes usando el ID de la conversación."
        
    def get_tools(self, all_available_tools: List[Callable]) -> List[Callable]:
        return [obtener_conversaciones_linkedin, enviar_mensaje_linkedin]
