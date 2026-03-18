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
    # Tabla simple de costos estimados (x 1,000,000 tokens) para la API de Gemini
    precio_in = 0.075
    precio_out = 0.30
    
    _lower_model = model.lower()
    
    if "pro" in _lower_model:
        # Precios base para Gemini Pro
        precio_in = 1.25
        precio_out = 5.00
    elif "lite" in _lower_model:
        # Precios base para Gemini Lite / 8B
        precio_in = 0.075
        precio_out = 0.30
    elif "flash" in _lower_model:
        # Precios de Flash (1.5)
        precio_in = 0.075
        precio_out = 0.30
        
    input_cost = (input_tokens / 1_000_000) * precio_in
    output_cost = (output_tokens / 1_000_000) * precio_out
    total_cost = input_cost + output_cost
    
    usage_record = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
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
