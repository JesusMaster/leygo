import json
import os
import uuid
from datetime import datetime

WEBHOOKS_FILE = "memoria/episodica/webhooks.json"

def get_webhooks_file_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, WEBHOOKS_FILE)

def load_webhooks() -> list:
    filepath = get_webhooks_file_path()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error cargando webhooks.json: {e}")
            return []
    return []

def save_webhooks(webhooks: list):
    filepath = get_webhooks_file_path()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(webhooks, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando webhooks.json: {e}")

def create_webhook(titulo: str, descripcion: str, modelo: str) -> dict:
    webhooks = load_webhooks()
    new_id = str(uuid.uuid4())
    
    new_wh = {
        "id": new_id,
        "titulo": titulo,
        "descripcion": descripcion,
        "modelo": modelo,
        "paused": False,
        "fecha_creacion": datetime.now().isoformat()
    }
    webhooks.append(new_wh)
    save_webhooks(webhooks)
    return new_wh

def update_webhook(webhook_id: str, titulo: str = None, descripcion: str = None, modelo: str = None, paused: bool = None) -> dict:
    webhooks = load_webhooks()
    updated_wh = None
    for wh in webhooks:
        if wh.get("id") == webhook_id:
            if titulo is not None:
                wh["titulo"] = titulo
            if descripcion is not None:
                wh["descripcion"] = descripcion
            if modelo is not None:
                wh["modelo"] = modelo
            if paused is not None:
                wh["paused"] = paused
            updated_wh = wh
            break
            
    if updated_wh:
        save_webhooks(webhooks)
        
    return updated_wh

def delete_webhook(webhook_id: str) -> bool:
    webhooks = load_webhooks()
    original_len = len(webhooks)
    webhooks = [wh for wh in webhooks if wh.get("id") != webhook_id]
    
    if len(webhooks) < original_len:
        save_webhooks(webhooks)
        return True
    return False

def get_webhook(webhook_id: str) -> dict:
    webhooks = load_webhooks()
    for wh in webhooks:
        if wh.get("id") == webhook_id:
            return wh
    return None
