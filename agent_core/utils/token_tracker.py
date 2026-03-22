import json
import os
import datetime

def get_history_path():
    # Calculamos la raíz de agent_core y llegamos a la subcarpeta 'memoria'
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "memoria", "usage_history.json")

def get_prices_from_json(model_id: str) -> tuple[float, float]:
    """
    Busca el precio por cada 1M de tokens en gemini_cost.json para el modelo específico.
    Retorna: (precio_in, precio_out)
    """
    # Defaults de seguridad
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
                
                # Extraer input
                in_data = standard.get("input", standard.get("input_text", standard.get("input_text_image", precio_in)))
                if isinstance(in_data, dict):
                    # Soporte para estructuras variables (<=200k vs texto plano)
                    precio_in = in_data.get("<=200k_prompt_tokens", 
                                in_data.get("text_image_video", 
                                in_data.get("text_per_1M_tokens", 
                                in_data.get("text", precio_in))))
                else:
                    precio_in = float(in_data)
                    
                # Extraer output
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

def log_token_usage(user_input: str, model: str, input_tokens: int, output_tokens: int, thread_id: str = "system"):
    """
    Registra el uso de tokens y el costo en el archivo historico.
    El costo se deduce dinámicamente desde gemini_cost.json.
    """
    # Buscar precios oficiales en el JSON
    precio_in, precio_out = get_prices_from_json(model)
    
    # Si la búsqueda fallara y devolviese 0 (salvaguarda por seguridad)
    if precio_in <= 0.0 or precio_out <= 0.0:
        _lower = model.lower()
        if "lite" in _lower:
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
