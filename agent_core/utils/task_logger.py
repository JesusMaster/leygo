"""
Task Execution Logger — registra cada ejecución de tareas programadas en SQLite.
Reutiliza la misma BD usage.db para mantener todo centralizado.
"""
import os
import sqlite3
import datetime
import threading
from zoneinfo import ZoneInfo

# ─── Thread-safe connection (one per thread) ────────────────────────────────────
_local = threading.local()

def _get_db_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "memoria", "usage.db")

def _get_conn() -> sqlite3.Connection:
    """Returns a thread-local SQLite connection, creating the table if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        db_path = _get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _local.conn = sqlite3.connect(db_path, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS task_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                task_name TEXT,
                timestamp TEXT NOT NULL,
                trigger_type TEXT DEFAULT 'scheduled',
                status TEXT DEFAULT 'running',
                result TEXT,
                error TEXT,
                duration_ms INTEGER DEFAULT 0
            )
        """)
        _local.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_log_task_id ON task_execution_log(task_id)
        """)
        _local.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_log_timestamp ON task_execution_log(timestamp)
        """)
        _local.conn.commit()
    return _local.conn


def log_task_start(task_id: str, task_name: str, trigger_type: str = "scheduled") -> int:
    """
    Registra el inicio de una ejecución de tarea.
    Retorna el row_id para luego actualizar con el resultado.
    """
    tz_str = os.getenv("TZ", "America/Santiago")
    timestamp = datetime.datetime.now(ZoneInfo(tz_str)).isoformat()
    
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "INSERT INTO task_execution_log (task_id, task_name, timestamp, trigger_type, status) VALUES (?, ?, ?, ?, 'running')",
            (task_id, task_name, timestamp, trigger_type)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"[TaskLogger] Error registrando inicio: {e}")
        return -1


def log_task_end(row_id: int, status: str, result: str = "", error: str = "", duration_ms: int = 0):
    """
    Actualiza un registro de ejecución con el resultado final.
    status: 'success' | 'error'
    """
    if row_id < 0:
        return
    
    # Truncar resultado para no explotar la BD
    if result and len(result) > 2000:
        result = result[:2000] + "... [truncado]"
    
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE task_execution_log SET status = ?, result = ?, error = ?, duration_ms = ? WHERE id = ?",
            (status, result, error, duration_ms, row_id)
        )
        conn.commit()
    except Exception as e:
        print(f"[TaskLogger] Error registrando fin: {e}")


def get_task_logs(task_id: str, limit: int = 50) -> list[dict]:
    """
    Devuelve las últimas `limit` ejecuciones de una tarea específica.
    """
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id, task_id, task_name, timestamp, trigger_type, status, result, error, duration_ms "
            "FROM task_execution_log WHERE task_id = ? ORDER BY id DESC LIMIT ?",
            (task_id, limit)
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "task_id": r[1],
                "task_name": r[2],
                "timestamp": r[3],
                "trigger_type": r[4],
                "status": r[5],
                "result": r[6] or "",
                "error": r[7] or "",
                "duration_ms": r[8]
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[TaskLogger] Error leyendo logs: {e}")
        return []


def get_all_task_logs(limit: int = 200) -> list[dict]:
    """
    Devuelve las últimas `limit` ejecuciones de TODAS las tareas.
    """
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id, task_id, task_name, timestamp, trigger_type, status, result, error, duration_ms "
            "FROM task_execution_log ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "task_id": r[1],
                "task_name": r[2],
                "timestamp": r[3],
                "trigger_type": r[4],
                "status": r[5],
                "result": r[6] or "",
                "error": r[7] or "",
                "duration_ms": r[8]
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[TaskLogger] Error leyendo todos los logs: {e}")
        return []
