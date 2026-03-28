import os
import requests
import json
from pathlib import Path
from dotenv import load_dotenv
from agent_core.sub_agents.base import BaseSubAgent
from langchain_core.tools import tool

# Cargar el .env del agente al importar el modulo
# Esto asegura que las variables esten disponibles para las herramientas
_agent_dir = Path(__file__).parent
load_dotenv(_agent_dir / ".env", override=False)


@tool
def consultar_agente_loopy(task: str) -> str:
    """
    Envia una tarea o consulta al ecosistema Loopy Thinking.
    Utiliza esta herramienta para delegar preguntas a agentes como Atlas
    cuando necesites obtener informacion de negocio, metricas o funcionalidades
    disponibles en Loopy.

    Args:
        task: La pregunta o tarea especifica a enviar al ecosistema Loopy.

    Returns:
        La respuesta del ecosistema Loopy en formato de texto.
    """
    api_url = os.environ.get("LOOPY_URL_ENDPOINT")
    session_key = os.environ.get("LOOPY_SESSION_KEY")
    agent_token = os.environ.get("LOOPY_AGENT_REGISTRY_TOKEN")

    if not api_url:
        return "Error: LOOPY_URL_ENDPOINT no esta configurado en el .env del agente loopybridge."
    if not session_key or not agent_token:
        return "Error: LOOPY_SESSION_KEY o LOOPY_AGENT_REGISTRY_TOKEN no estan configurados en el .env del agente loopybridge."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {agent_token}",
    }

    payload = {
        "session_key": session_key,
        "intent": "general",
        "message": task,
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        if response.status_code == 200:
            try:
                return json.dumps(response.json(), indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                return response.text
        else:
            return (
                f"Error al contactar la API de Loopy. "
                f"Codigo: {response.status_code}. Respuesta: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        return f"Error de conexion al intentar contactar la API de Loopy: {e}"


class LoopybridgeAgent(BaseSubAgent):

    @property
    def name(self):
        return "loopybridge"

    @property
    def description(self):
        return "Agente intermediario para interactuar con el ecosistema de agentes Loopy. Consulta informacion de negocio, metricas y funcionalidades disponibles en Loopy Thinking."

    def get_tools(self, all_available_tools: list = None):
        # Re-cargar .env por si cambio despues de que el modulo fue importado
        load_dotenv(_agent_dir / ".env", override=True)
        return [consultar_agente_loopy]