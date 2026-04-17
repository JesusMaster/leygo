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

# ─── Pricing ────────────────────────────────────────────────────────────────────
def get_prices_from_json(model_id: str) -> tuple[float, float]:
    """
    Busca el precio por cada 1M de tokens en gemini_cost.json para el modelo específico.
    Retorna: (precio_in, precio_out)
    """
    if model_id.startswith("ollama/"):
        return 0.0, 0.0

    precio_in = 0.50
    precio_out = 3.00

    json_path = os.path.join(os.path.dirname(__file__), "gemini_cost.json")
    if not os.path.exists(json_path):
        return precio_in, precio_out

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for model in data.get("models", []):
            if model_id in model.get("model_ids", []):
                standard = model.get("pricing", {}).get("standard", {})

                in_data = standard.get("input", standard.get("input_text", standard.get("input_text_image", precio_in)))
                if isinstance(in_data, dict):
                    precio_in = in_data.get("<=200k_prompt_tokens",
                                in_data.get("text_image_video",
                                in_data.get("text_per_1M_tokens",
                                in_data.get("text", precio_in))))
                else:
                    precio_in = float(in_data)

                out_data = standard.get("output_including_thinking", standard.get("output_text_and_thinking", standard.get("output", precio_out)))
                if isinstance(out_data, dict):
                    precio_out = out_data.get("<=200k_prompt_tokens",
                                 out_data.get("text", precio_out))
                else:
                    precio_out = float(out_data)

                return float(precio_in), float(precio_out)
    except Exception as e:
        print(f"Error parseando gemini_cost.json: {e}")

    return precio_in, precio_out

# ─── Core: Log Usage ────────────────────────────────────────────────────────────
def log_token_usage(user_input: str, model: str, input_tokens: int, output_tokens: int, thread_id: str = "system"):
    """
    Registra el uso de tokens y el costo en la base de datos SQLite.
    """
    precio_in, precio_out = get_prices_from_json(model)

    if (precio_in <= 0.0 or precio_out <= 0.0) and not model.startswith("ollama/"):
        _lower = model.lower()
        # Anthropic Claude pricing (per 1M tokens)
        if "claude" in _lower:
            if "opus" in _lower:
                precio_in, precio_out = 15.00, 75.00
            elif "sonnet" in _lower:
                precio_in, precio_out = 3.00, 15.00
            elif "haiku" in _lower:
                precio_in, precio_out = 0.25, 1.25
            else:
                precio_in, precio_out = 3.00, 15.00
        # OpenAI pricing (per 1M tokens)
        elif "gpt" in _lower or _lower.startswith("o1") or _lower.startswith("o3") or _lower.startswith("o4"):
            if "gpt-4o-mini" in _lower:
                precio_in, precio_out = 0.15, 0.60
            elif "gpt-4o" in _lower:
                precio_in, precio_out = 2.50, 10.00
            elif "gpt-4-turbo" in _lower:
                precio_in, precio_out = 10.00, 30.00
            elif _lower.startswith("o1"):
                precio_in, precio_out = 15.00, 60.00
            elif _lower.startswith("o3"):
                precio_in, precio_out = 2.00, 8.00
            elif _lower.startswith("o4"):
                precio_in, precio_out = 2.00, 8.00
            else:
                precio_in, precio_out = 2.50, 10.00  # Default OpenAI
        # Gemini fallback pricing
        elif "lite" in _lower:
            precio_in, precio_out = 0.25, 1.50
        elif "pro" in _lower:
            precio_in, precio_out = 2.00, 12.00
        else:
            precio_in, precio_out = 0.50, 3.00

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
