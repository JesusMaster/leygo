import os
import sqlite3
import datetime
import json
import threading

# ─── Paths ──────────────────────────────────────────────────────────────────────
def _get_db_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "memoria", "bds", "usage.db")

def _get_old_json_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "memoria", "usage_history.json")

# ─── Thread-safe connection (one per thread) ────────────────────────────────────
_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    """Returns a thread-local SQLite connection, creating the table if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        db_path = _get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _local.conn = sqlite3.connect(db_path, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent writes
        _local.conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_input TEXT,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                thread_id TEXT DEFAULT 'system'
            )
        """)
        _local.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_history(timestamp)
        """)
        _local.conn.commit()
    return _local.conn

# ─── Pricing (Auto-Update via LiteLLM) ──────────────────────────────────────────
LITELLM_PRICING_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

def _ensure_litellm_pricing_json() -> dict:
    """
    Ensure the litellm pricing JSON is downloaded and at most 7 days old.
    Returns the parsed JSON data.
    """
    json_path = os.path.join(os.path.dirname(__file__), "litellm_cost.json")
    
    # Check if download is needed (doesn't exist or is older than 7 days)
    needs_download = True
    if os.path.exists(json_path):
        file_age = datetime.datetime.now().timestamp() - os.path.getmtime(json_path)
        if file_age < (7 * 24 * 60 * 60):  # 7 days
            needs_download = False
            
    if needs_download:
        try:
            import urllib.request
            print(f"[Pricing] Descargando precios actualizados desde LiteLLM...")
            req = urllib.request.Request(LITELLM_PRICING_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return data
        except Exception as e:
            print(f"[Pricing] Error descargando litellm json ({e}). Usando caché local si existe.")
            
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def get_prices(model_id: str) -> tuple[float, float]:
    """
    Busca el precio por cada 1M de tokens usando el registro comunitario de LiteLLM de forma dinámica.
    Retorna: (precio_in_1M, precio_out_1M).
    """
    if model_id.startswith("ollama/") or "ollama" in model_id.lower():
        return 0.0, 0.0

    # Sanitize model id to match litellm's keys
    search_id = model_id.lower().replace("openai/", "").replace("anthropic/", "").replace("google/", "")

    # 1. Intentar con tabla de LiteLLM (automática)
    litellm_data = _ensure_litellm_pricing_json()
    if litellm_data and search_id in litellm_data:
        m_data = litellm_data[search_id]
        in_cost_1k = m_data.get("input_cost_per_token", 0.0) * 1_000_000
        out_cost_1k = m_data.get("output_cost_per_token", 0.0) * 1_000_000
        if in_cost_1k > 0 or out_cost_1k > 0:
            return float(in_cost_1k), float(out_cost_1k)
            
    # Fallback heurístico para modelos nuevos y desconocidos que no estén en JSON
    if "claude-3-5-sonnet" in search_id or "claude-sonnet-4.6" in search_id:
        return 3.00, 15.00
    if "claude-3-haiku" in search_id or "claude-haiku-4.5" in search_id:
        return 1.00, 5.00
    if "gpt-4o-mini" in search_id or "gpt-5.4-mini" in search_id:
        return 0.15, 0.60
    if "gpt-4o" in search_id or "gpt-5.4" in search_id:
        return 2.50, 10.00
    if "gemini-2.5-flash" in search_id:
        return 0.15, 0.60
    if "gemini-3" in search_id:
        return 2.50, 10.00

    return 2.50, 10.00  # Default general


# ─── Core: Log Usage ────────────────────────────────────────────────────────────
def log_token_usage(user_input: str, model: str, input_tokens: int, output_tokens: int, thread_id: str = "system"):
    """
    Registra el uso de tokens y el costo en la base de datos SQLite.
    """
    precio_in, precio_out = get_prices(model)

    input_cost = (input_tokens / 1_000_000) * precio_in
    output_cost = (output_tokens / 1_000_000) * precio_out
    total_cost = input_cost + output_cost

    from zoneinfo import ZoneInfo
    tz_str = os.getenv("TZ", "America/Santiago")

    timestamp = datetime.datetime.now(ZoneInfo(tz_str)).isoformat()
    truncated_input = (user_input[:100] + "...") if user_input and len(user_input) > 100 else (user_input or "")

    usage_record = {
        "timestamp": timestamp,
        "user_input": truncated_input,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": total_cost,
        "thread_id": thread_id
    }

    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO usage_history (timestamp, user_input, model, input_tokens, output_tokens, cost_usd, thread_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (timestamp, truncated_input, model, input_tokens, output_tokens, total_cost, thread_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error guardando uso de tokens en SQLite: {e}")

    return usage_record

# ─── Query: Current Month Cost ──────────────────────────────────────────────────
def get_current_month_cost() -> float:
    """
    Calcula el costo total (USD) acumulado durante el mes actual.
    """
    try:
        from zoneinfo import ZoneInfo
        tz_str = os.getenv("TZ", "America/Santiago")
        now = datetime.datetime.now(ZoneInfo(tz_str))
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        conn = _get_conn()
        cursor = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM usage_history WHERE timestamp >= ?",
            (month_start,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0.0
    except Exception as e:
        print(f"Error calculando costo mensual desde SQLite: {e}")
        return 0.0

# ─── Query: Full History ─────────────────────────────────────────────────────────
def get_usage_history(limit: int = 1000) -> list[dict]:
    """
    Devuelve las últimas `limit` entradas del historial de uso.
    """
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT timestamp, user_input, model, input_tokens, output_tokens, cost_usd, thread_id FROM usage_history ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        # Devolver en orden cronológico (el query es DESC para limitar, lo invertimos)
        results = []
        for row in reversed(rows):
            results.append({
                "timestamp": row[0],
                "user_input": row[1],
                "model": row[2],
                "input_tokens": row[3],
                "output_tokens": row[4],
                "cost_usd": row[5],
                "thread_id": row[6]
            })
        return results
    except Exception as e:
        print(f"Error leyendo historial de uso desde SQLite: {e}")
        return []

# ─── Budget Check ────────────────────────────────────────────────────────────────
def check_budget_exceeded() -> tuple[bool, str]:
    """
    Verifica si se ha excedido el presupuesto mensual.
    Retorna (is_exceeded, message).
    """
    try:
        from dotenv import dotenv_values
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        config = dotenv_values(env_path)
        budget_str = config.get("MONTHLY_BUDGET_USD", "")

        if budget_str:
            budget = float(budget_str)
            current_cost = get_current_month_cost()
            if current_cost >= budget:
                msg = f"⚠️ *Cuota Mensual Excedida* ⚠️\n\nHas superado tu límite de gasto mensual de *${budget} USD*. El uso de modelos ha sido suspendido.\n\nPor favor, amplía el límite en la pestaña de 'Uso de Tokens' para continuar consultando a Leygo AI."
                return True, msg
    except Exception as e:
        print(f"Error comprobando el budget: {e}")

    return False, ""
