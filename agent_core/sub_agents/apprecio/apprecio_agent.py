import os
import json
import time
import hashlib
import requests
from typing import Dict, Any, Optional
from ..base import BaseSubAgent

class ApprecioApiClient:
    def __init__(self, api_url: str, public_token: str, private_token: str):
        self.api_url = api_url
        self.public_token = public_token
        self.private_token = private_token

    def _generate_hash(self, ts: int) -> str:
        data = f"{ts}{self.public_token}{self.private_token}"
        return hashlib.md5(data.encode('utf-8')).hexdigest()

    def make_request(self, accion: str, additional_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if additional_data is None:
            additional_data = {}
        
        ts = int(time.time())
        hash_value = self._generate_hash(ts)
        
        form_data = {
            'accion': accion,
            'public_token': self.public_token,
            'ts': str(ts),
            'hash': hash_value,
            'tipo': 'JSON'
        }
        form_data.update(additional_data)
        
        try:
            response = requests.post(
                self.api_url,
                data=form_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

def _get_credentials():
    """Lee las credenciales desde el archivo de configuracion o pide configurarlas."""
    path = "agent_core/sub_agents/apprecio/files/credentials.json"
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)

def configurar_credenciales_apprecio(api_url: str, public_token: str, private_token: str) -> str:
    """
    Guarda las credenciales de la API de Apprecio para su uso futuro.
    api_url: URL de la API (ej. https://api.apprecio.cl/api)
    public_token: Token publico
    private_token: Token privado
    """
    os.makedirs("agent_core/sub_agents/apprecio/files", exist_ok=True)
    path = "agent_core/sub_agents/apprecio/files/credentials.json"
    creds = {
        "api_url": api_url,
        "public_token": public_token,
        "private_token": private_token
    }
    with open(path, "w") as f:
        json.dump(creds, f)
    return "Credenciales guardadas exitosamente."

def consultar_saldo_empresa() -> str:
    """Consulta el saldo de la empresa en Apprecio."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas. Usa configurar_credenciales_apprecio primero."
    client = ApprecioApiClient(**creds)
    res = client.make_request("saldoEmpresa")
    return json.dumps(res)

def cargar_puntos_email(email: str, asignado: float, descripcion: str) -> str:
    """Agrega puntos a un usuario identificado por su email."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("carga_directa_email", {"email": email, "asignado": asignado, "descripcion": descripcion})
    return json.dumps(res)

def acumular_puntos_rut(rut: str, asignado: float, descripcion: str) -> str:
    """Agrega puntos a un usuario identificado por su RUT/DNI/CEDULA."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("acumular_puntos", {"rut": rut, "asignado": asignado, "descripcion": descripcion})
    return json.dumps(res)

def consultar_saldo_email(email: str) -> str:
    """Consulta el saldo de un usuario identificado por su email."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("saldo_usuario_email", {"email": email})
    return json.dumps(res)

def consultar_saldo_rut(rut: str) -> str:
    """Consulta el saldo de un usuario identificado por su RUT/DNI/CEDULA."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("saldo_usuario", {"rut": rut})
    return json.dumps(res)

def obtener_historial_carga(date_start: str, date_end: str) -> str:
    """Obtiene el historial de carga para un rango de fechas (YYYY-mm-dd)."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("historialCarga", {"date_start": date_start, "date_end": date_end})
    return json.dumps(res)

def obtener_listado_giftcards() -> str:
    """Obtiene la lista de gift cards disponibles."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("getListadoGiftcard")
    return json.dumps(res)

def consultar_stock_giftcard(id_giftcard: int) -> str:
    """Consulta el stock de una gift card especifica."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("getStockGc", {"idGiftcard": id_giftcard})
    return json.dumps(res)

def canjear_giftcard(id_giftcard: int, valor: float, user_code: str, user_name: str) -> str:
    """Canjea una gift card para un usuario especifico."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("reedemGifCard", {
        "idGiftcard": id_giftcard,
        "valor": valor,
        "userCode": user_code,
        "userName": user_name
    })
    return json.dumps(res)

def consultar_giftcard_personalizada(codigo: str) -> str:
    """Consulta los detalles de una gift card especifica por su codigo."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("consultaGiftcard", {"codigo": codigo})
    return json.dumps(res)

def utilizar_giftcard_personalizada(codigo: str, valor_compra: float) -> str:
    """Utiliza una gift card por su codigo para una compra."""
    creds = _get_credentials()
    if not creds: return "Error: Credenciales no configuradas."
    client = ApprecioApiClient(**creds)
    res = client.make_request("utilizarGiftcard", {"codigo": codigo, "valorCompra": valor_compra})
    return json.dumps(res)

class ApprecioAgent(BaseSubAgent):
    @property
    def model(self):
        return "gemini-3.1-flash-lite-preview"
    
    @property
    def name(self):
        return "apprecio"
    
    @property
    def description(self):
        return "Agente para interactuar con la API de Apprecio (puntos, giftcards, saldos)."
    
    @property
    def system_prompt(self):
        return "Eres el agente Apprecio. Tu funcion es gestionar puntos, saldos y giftcards usando la API de Apprecio. Si no tienes credenciales configuradas, pide al usuario que use la herramienta configurar_credenciales_apprecio."
    
    def get_tools(self, all_available_tools):
        return [
            configurar_credenciales_apprecio,
            consultar_saldo_empresa,
            cargar_puntos_email,
            acumular_puntos_rut,
            consultar_saldo_email,
            consultar_saldo_rut,
            obtener_historial_carga,
            obtener_listado_giftcards,
            consultar_stock_giftcard,
            canjear_giftcard,
            consultar_giftcard_personalizada,
            utilizar_giftcard_personalizada
        ]