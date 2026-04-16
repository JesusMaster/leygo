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

import sqlite3
import threading

WEBHOOKS_DB_FILE = "memoria/webhooks.db"
WEBHOOK_LOGS_FILE_OLD = "memoria/episodica/webhook_logs.json"

_local = threading.local()

def _get_db_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, WEBHOOKS_DB_FILE)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        _local.conn = sqlite3.connect(db_path, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT,
                response TEXT,
                error TEXT
            )
        """)
        _local.conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_logs_timestamp ON webhook_logs(timestamp DESC)")
        _local.conn.commit()
        
        # Migración automática desde JSON viejo
        old_json_path = os.path.join(base_dir, WEBHOOK_LOGS_FILE_OLD)
        if os.path.exists(old_json_path):
            try:
                # Chequear si ya migramos (si la tabla está vacía)
                c = _local.conn.execute("SELECT COUNT(*) FROM webhook_logs")
                count = c.fetchone()[0]
                if count == 0:
                    with open(old_json_path, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                    
                    for log in reversed(logs):  # Insertar del más antiguo al más nuevo para mantener IDs correctos
                        _local.conn.execute(
                            "INSERT INTO webhook_logs (webhook_id, timestamp, payload, response, error) VALUES (?, ?, ?, ?, ?)",
                            (log.get("webhook_id", ""), log.get("timestamp", ""), log.get("payload", ""), log.get("response", ""), log.get("error"))
                        )
                    _local.conn.commit()
                # Renombrar JSON viejo a .bak para evitar futuras migraciones
                os.rename(old_json_path, old_json_path + ".bak")
            except Exception as e:
                print(f"Error migrando webhooks_logs JSON a SQLite: {e}")
                
    return _local.conn

def log_webhook_execution(webhook_id: str, payload, response: str, error: str = None):
    # Safe payload parsing
    if isinstance(payload, dict):
        payload_str = json.dumps(payload, ensure_ascii=False)
    else:
        payload_str = str(payload)
        
    truncated_payload = payload_str[:150] + ("..." if len(payload_str) > 150 else "")
    ts = datetime.now().isoformat()
    
    conn = _get_db_conn()
    try:
        conn.execute(
            "INSERT INTO webhook_logs (webhook_id, timestamp, payload, response, error) VALUES (?, ?, ?, ?, ?)",
            (webhook_id, ts, truncated_payload, response, error)
        )
        conn.commit()
        
        # Cleanup logs más viejos de 200 (mantiene el límite para evitar DB pesada si es muy frecuente)
        conn.execute("""
            DELETE FROM webhook_logs 
            WHERE id NOT IN (
                SELECT id FROM webhook_logs ORDER BY timestamp DESC LIMIT 200
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"Error guardando log SQLite de webhook: {e}")

def get_webhook_logs(webhook_id: str = None) -> list:
    conn = _get_db_conn()
    try:
        if webhook_id:
            cursor = conn.execute(
                "SELECT webhook_id, timestamp, payload, response, error FROM webhook_logs WHERE webhook_id = ? ORDER BY timestamp DESC",
                (webhook_id,)
            )
        else:
            cursor = conn.execute(
                "SELECT webhook_id, timestamp, payload, response, error FROM webhook_logs ORDER BY timestamp DESC"
            )
            
        logs = []
        for row in cursor.fetchall():
            logs.append({
                "webhook_id": row[0],
                "timestamp": row[1],
                "payload": row[2],
                "response": row[3],
                "error": row[4]
            })
        return logs
    except Exception as e:
        print(f"Error leyendo logs SQLite de webhook: {e}")
        return []
