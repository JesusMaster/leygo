import json
import os
import datetime

def get_history_path():
    # Calculamos la raíz de agent_core y llegamos a la subcarpeta 'memoria'
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "memoria", "usage_history.json")

def log_token_usage(user_input: str, model: str, input_tokens: int, output_tokens: int, thread_id: str = "system"):
    """
    Registra el uso de tokens y el costo en el archivo historico.
    El costo se deduce dinámicamente según la familia del modelo ingresado.
    """
    # Tabla de precios por 1,000,000 de tokens (actualizada Q1 2026 para Serie 3.1)
    # Valores default por si no hace match
    precio_in = 0.50
    precio_out = 3.00
    
    _lower_model = model.lower()
    
    if "pro" in _lower_model:
        # Precios para gemini-3.1-pro-preview (<200k context)
        precio_in = 2.00
        precio_out = 12.00
    elif "lite" in _lower_model:
        # Precios para gemini-3.1-flash-lite-preview (texto)
        precio_in = 0.25
        precio_out = 1.50
    elif "flash" in _lower_model:
        # Precios para gemini-3-flash-preview (y variantes estándar)
        precio_in = 0.50
        precio_out = 3.00
        
    input_cost = (input_tokens / 1_000_000) * precio_in
    output_cost = (output_tokens / 1_000_000) * precio_out
    total_cost = input_cost + output_cost
    
    from zoneinfo import ZoneInfo
    tz_str = os.getenv("TZ", "America/Santiago")
    
    usage_record = {
        "timestamp": datetime.datetime.now(ZoneInfo(tz_str)).isoformat(),
        "user_input": user_input[:100] if user_input else "",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": total_cost,
        "thread_id": thread_id
    }
    
    history_path = get_history_path()
    try:
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        history = []
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    history = json.loads(content)
        history.append(usage_record)
        history = history[-1000:]
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
            
        return usage_record
    except Exception as e:
        print(f"Error guardando historial de uso de tokens: {e}")
        return usage_record

def get_current_month_cost() -> float:
    """
    Calcula el costo total (USD) acumulado durante el mes actual.
    """
    history_path = get_history_path()
    if not os.path.exists(history_path):
        return 0.0
        
    try:
        from zoneinfo import ZoneInfo
        tz_str = os.getenv("TZ", "America/Santiago")
        now = datetime.datetime.now(ZoneInfo(tz_str))
        
        with open(history_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return 0.0
            history = json.loads(content)
            
        total_cost = 0.0
        for record in history:
            try:
                record_time = datetime.datetime.fromisoformat(record["timestamp"])
                # Verificar si es el mes actual y año actual
                if record_time.month == now.month and record_time.year == now.year:
                    total_cost += record.get("cost_usd", 0.0)
            except:
                pass
                
        return total_cost
    except Exception as e:
        print(f"Error calculando el costo del mes actual: {e}")
        return 0.0

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
