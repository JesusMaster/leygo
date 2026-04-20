import json
import os
import uuid
import sqlite3
import threading
from datetime import datetime
from typing import Optional

WEBHOOKS_DB_FILE = "memoria/bds/webhooks.db"
WEBHOOKS_FILE_OLD = "memoria/episodica/webhooks.json"
WEBHOOK_LOGS_FILE_OLD = "memoria/episodica/webhook_logs.json"

_local = threading.local()

def _init_db_schema(conn: sqlite3.Connection):
    # Tabla de Webhooks (Configuración)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id TEXT PRIMARY KEY,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            modelo TEXT,
            paused BOOLEAN DEFAULT 0,
            fecha_creacion TEXT
        )
    """)
    # Tabla de Logs de Ejecucción
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload TEXT,
            response TEXT,
            error TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_logs_timestamp ON webhook_logs(timestamp DESC)")
    conn.commit()

def _migrate_webhooks_json(conn: sqlite3.Connection, base_dir: str):
    old_config_path = os.path.join(base_dir, WEBHOOKS_FILE_OLD)
    if os.path.exists(old_config_path):
        try:
            c = conn.execute("SELECT COUNT(*) FROM webhooks")
            if c.fetchone()[0] == 0:
                with open(old_config_path, "r", encoding="utf-8") as f:
                    whs = json.load(f)
                for wh in whs:
                    conn.execute(
                        "INSERT INTO webhooks (id, titulo, descripcion, modelo, paused, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?)",
                        (wh.get("id"), wh.get("titulo"), wh.get("descripcion"), wh.get("modelo"), 1 if wh.get("paused") else 0, wh.get("fecha_creacion"))
                    )
                conn.commit()
            # Renombrar JSON viejo a .bak para evitar futuras migraciones
            os.rename(old_config_path, old_config_path + ".bak")
        except Exception as e:
            print(f"Error migrando webhooks JSON a SQLite: {e}")

def _migrate_webhook_logs_json(conn: sqlite3.Connection, base_dir: str):
    old_logs_path = os.path.join(base_dir, WEBHOOK_LOGS_FILE_OLD)
    if os.path.exists(old_logs_path):
        try:
            c = conn.execute("SELECT COUNT(*) FROM webhook_logs")
            if c.fetchone()[0] == 0:
                with open(old_logs_path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                for log in reversed(logs):
                    conn.execute(
                        "INSERT INTO webhook_logs (webhook_id, timestamp, payload, response, error) VALUES (?, ?, ?, ?, ?)",
                        (log.get("webhook_id", ""), log.get("timestamp", ""), log.get("payload", ""), log.get("response", ""), log.get("error"))
                    )
                conn.commit()
            os.rename(old_logs_path, old_logs_path + ".bak")
        except Exception as e:
            print(f"Error migrando webhooks_logs JSON a SQLite: {e}")

def _get_db_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, WEBHOOKS_DB_FILE)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        _local.conn = sqlite3.connect(db_path, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
        _local.conn.execute("PRAGMA journal_mode=WAL")
        
        _init_db_schema(_local.conn)
        _migrate_webhooks_json(_local.conn, base_dir)
        _migrate_webhook_logs_json(_local.conn, base_dir)
                
    return _local.conn

def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "descripcion": row["descripcion"],
        "modelo": row["modelo"],
        "paused": bool(row["paused"]),
        "fecha_creacion": row["fecha_creacion"]
    }

def load_webhooks() -> list:
    conn = _get_db_conn()
    cursor = conn.execute("SELECT * FROM webhooks ORDER BY fecha_creacion DESC")
    return [_row_to_dict(row) for row in cursor.fetchall()]

def create_webhook(titulo: str, descripcion: str, modelo: str) -> dict:
    conn = _get_db_conn()
    new_id = str(uuid.uuid4())
    fecha_creacion = datetime.now().isoformat()
    
    conn.execute(
        "INSERT INTO webhooks (id, titulo, descripcion, modelo, paused, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, titulo, descripcion, modelo, 0, fecha_creacion)
    )
    conn.commit()
    
    return {
        "id": new_id,
        "titulo": titulo,
        "descripcion": descripcion,
        "modelo": modelo,
        "paused": False,
        "fecha_creacion": fecha_creacion
    }

def update_webhook(webhook_id: str, titulo: str = None, descripcion: str = None, modelo: str = None, paused: bool = None) -> Optional[dict]:
    conn = _get_db_conn()
    # Update solo si hay info
    updates = []
    params = []
    if titulo is not None:
        updates.append("titulo = ?")
        params.append(titulo)
    if descripcion is not None:
        updates.append("descripcion = ?")
        params.append(descripcion)
    if modelo is not None:
        updates.append("modelo = ?")
        params.append(modelo)
    if paused is not None:
        updates.append("paused = ?")
        params.append(1 if paused else 0)
        
    if not updates:
        return get_webhook(webhook_id)
        
    params.append(webhook_id)
    query = f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?"
    
    conn.execute(query, tuple(params))
    conn.commit()
    return get_webhook(webhook_id)

def delete_webhook(webhook_id: str) -> bool:
    conn = _get_db_conn()
    cursor = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    conn.execute("DELETE FROM webhook_logs WHERE webhook_id = ?", (webhook_id,))
    conn.commit()
    return cursor.rowcount > 0

def get_webhook(webhook_id: str) -> Optional[dict]:
    conn = _get_db_conn()
    cursor = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))
    row = cursor.fetchone()
    if row:
        return _row_to_dict(row)
    return None

def log_webhook_execution(webhook_id: str, payload, response: str, error: str = None):
    # Safe payload parsing
    if isinstance(payload, dict):
        payload_str = json.dumps(payload, ensure_ascii=False)
    else:
        payload_str = str(payload)
        
    # ts = datetime.now().isoformat()
    ts = datetime.now().isoformat()
    
    conn = _get_db_conn()
    try:
        conn.execute(
            "INSERT INTO webhook_logs (webhook_id, timestamp, payload, response, error) VALUES (?, ?, ?, ?, ?)",
            (webhook_id, ts, payload_str, response, error)
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
