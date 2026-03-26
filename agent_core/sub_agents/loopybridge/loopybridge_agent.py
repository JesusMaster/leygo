import os
import requests
import json
from langchain_core.tools import tool
from agent_core.sub_agents.base import BaseSubAgent

# Cargar variables de entorno del agente
_agent_dir = os.path.dirname(os.path.abspath(__file__))

def _get_headers():
    token = os.getenv("LOOPY_AGENT_REGISTRY_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def _get_session_key():
    return os.getenv("LOOPY_SESSION_KEY", "")

BRIDGE_URL = "https://efsyebiumgieglwvxiss.supabase.co/functions/v1/mc-bridge/a2a/inbound"


@tool
def registrar_agente(agent_id: str, name: str, role: str, responsibilities: str) -> str:
    """
    Registra un nuevo agente en el ecosistema de Loopy Thinking.
    El parametro responsibilities debe ser una lista de responsabilidades separadas por comas.
    """
    session_key = _get_session_key()
    if not session_key:
        return "Error: LOOPY_SESSION_KEY no esta configurado en el .env del agente loopy_bridge."

    responsibilities_list = [r.strip() for r in responsibilities.split(",") if r.strip()]

    payload = {
        "session_key": session_key,
        "intent": "register_agents",
        "message": "Registro de agentes",
        "context": {
            "agent_registry_update": True,
            "agents": [
                {
                    "agent_id": agent_id,
                    "name": name,
                    "role": role,
                    "responsibilities": responsibilities_list
                }
            ]
        }
    }

    try:
        response = requests.post(BRIDGE_URL, headers=_get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return f"Agente '{name}' registrado exitosamente en Loopy. Respuesta: {response.json()}"
    except requests.exceptions.HTTPError as e:
        return f"Error HTTP al registrar '{name}': {e}. Respuesta: {e.response.text if e.response else 'N/A'}"
    except requests.exceptions.RequestException as e:
        return f"Error de red al contactar Loopy Bridge: {e}"


@tool
def enviar_senal(intent: str, message: str, context_json: str) -> str:
    """
    Envia una senal al ecosistema de Loopy Thinking con un intent especifico.
    El parametro context_json debe ser un JSON valido como string.
    Intents utiles: 'query_nova', 'query_atlas', 'query_vega', 'query_echo', 'query_orion', 'query_cron'.
    """
    session_key = _get_session_key()
    if not session_key:
        return "Error: LOOPY_SESSION_KEY no esta configurado."

    try:
        context = json.loads(context_json) if context_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"Error: context_json no es un JSON valido: {e}"

    payload = {
        "session_key": session_key,
        "intent": intent,
        "message": message,
        "context": context
    }

    try:
        response = requests.post(BRIDGE_URL, headers=_get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return f"Senal '{intent}' enviada. Respuesta: {response.json()}"
    except requests.exceptions.HTTPError as e:
        return f"Error HTTP enviando senal '{intent}': {e}. Respuesta: {e.response.text if e.response else 'N/A'}"
    except requests.exceptions.RequestException as e:
        return f"Error de red: {e}"


# ── Clase del Agente ─────────────────────────────────────────────────────────

class LoopyBridgeAgent(BaseSubAgent):
    """
    Agente puente (bridge) para comunicacion con el ecosistema de Loopy Thinking.
    Gestiona registros de agentes y envio de senales A2A al endpoint mc-bridge.
    """

    @property
    def name(self) -> str:
        return "loopybridge"

    @property
    def description(self) -> str:
        return "Agente embajador diplomatico A2A para el ecosistema Loopy Thinking. Registra agentes y envia senales a Nova, Atlas, Vega, Echo, Orion y Cron."

    def get_tools(self, all_available_tools: list = None):
        # Cargar .env del agente en tiempo de ejecucion
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_agent_dir, ".env"), override=False)
        return [
            registrar_agente,
            enviar_senal,
        ]
