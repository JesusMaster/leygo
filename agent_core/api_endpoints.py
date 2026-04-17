from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import os
import sys
import asyncio
from dotenv import dotenv_values

# Añadir el path para importar el agente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import discover_sub_agents
from scheduler_manager import scheduler, guardar_estado_jobs, get_all_jobs, send_telegram_reminder, send_dynamic_telegram_reminder, execute_agent_task
from webhooks_manager import load_webhooks, create_webhook, update_webhook, delete_webhook, get_webhook, log_webhook_execution, get_webhook_logs
import status_bus
import json
from datetime import datetime
import shutil

router = APIRouter(prefix="/api")

class MessageRequest(BaseModel):
    message: str
    thread_id: str = "gui_session"

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str

class TaskCreateRequest(BaseModel):
    message_or_prompt: str
    type: str  # "date" or "interval"
    value: str  # ISO date string or minutes as string
    chat_id: str = "default_session"
    is_agent_action: bool = False

class TaskUpdateRequest(BaseModel):
    message_or_prompt: str

class WebhookCreateRequest(BaseModel):
    titulo: str
    descripcion: str
    modelo: str

class WebhookUpdateRequest(BaseModel):
    titulo: str = None
    descripcion: str = None
    modelo: str = None
    paused: bool = None

@router.get("/agents")
async def get_agents():
    """Devuelve la lista de agentes y sus herramientas."""
    try:
        agents = discover_sub_agents()
        result = []
        for a in agents:
            tools_list = []
            # Obtener nombres de herramientas
            # En el discovery, las herramientas se obtienen vía get_tools()
            # que requiere la lista de todas las herramientas disponibles.
            # Como aquí solo queremos metadatos, intentaremos obtener las funciones de forma segura.
            # Nota: Esto es aproximado para la UI.
            try:
                # Intentamos obtener herramientas sin inyectar las globales
                dummy_tools = a.get_tools([])
                for t in dummy_tools:
                    # Para evitar "AttributeError" al evaluar t.__name__ o t.__doc__ cuando
                    # t es una herramienta de clase (como StructuredTool de langchain), usamos
                    # getattr o hasattr adecuadamente.
                    t_name = getattr(t, "name", None) or getattr(t, "__name__", "Sin nombre")
                    t_desc = getattr(t, "description", None) or getattr(t, "__doc__", "Sin descripción")
                    if not t_desc:
                        t_desc = "Sin descripción"
                        
                    tools_list.append({
                        "name": t_name,
                        "description": str(t_desc).strip()
                    })
            except Exception as e:
                print(f"[get_agents UI] Advertencia: fallo extrayendo herramientas de {a.name}: {e}")

            result.append({
                "name": a.name,
                "description": a.description,
                "model": getattr(a, "model", "default"),
                "tools": tools_list
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """Eliminar un sub-agente por su nombre, borrando su carpeta."""
    if agent_name in ["assistant", "dev", "researcher", "mcp"]: # Proteger agentes base core
        raise HTTPException(status_code=403, detail="No puedes eliminar los agentes base del sistema.")
        
    try:
        agent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sub_agents", agent_name)
        if os.path.exists(agent_dir) and os.path.isdir(agent_dir):
            import shutil
            shutil.rmtree(agent_dir)
            return {"status": "success", "message": f"Agente '{agent_name}' eliminado correctamente."}
        else:
            raise HTTPException(status_code=404, detail="El agente especificado no existe o no es una carpeta.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error borrando agente: {str(e)}")

class AgentUpdateRequest(BaseModel):
    python_code: str = None
    episodic_code: str = None
    procedural_code: str = None
    prefs_code: str = None
    env_code: str = None

@router.get("/agents/{agent_name}")
async def get_agent_files(agent_name: str):
    """Obtiene los archivos fuente de un sub-agente (Python, episodic, procedural, prefs, env)."""
    agent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sub_agents", agent_name)
    if not os.path.exists(agent_dir) or not os.path.isdir(agent_dir):
        raise HTTPException(status_code=404, detail="El sub-agente no existe")
        
    py_path = os.path.join(agent_dir, f"{agent_name}_agent.py")
    mem_dir = os.path.join(agent_dir, "memoria")
    ep_path = os.path.join(mem_dir, "memoria_episodica.md")
    pr_path = os.path.join(mem_dir, "memoria_procedimental.md")
    prefs_path = os.path.join(mem_dir, "usuarios_preferencias.md")
    env_path = os.path.join(agent_dir, ".env")
    
    def read_safe(path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""
        
    return {
        "python_code": read_safe(py_path),
        "episodic_code": read_safe(ep_path),
        "procedural_code": read_safe(pr_path),
        "prefs_code": read_safe(prefs_path),
        "env_code": read_safe(env_path)
    }

@router.put("/agents/{agent_name}")
async def update_agent_files(agent_name: str, req: AgentUpdateRequest, request: Request):
    """Actualiza y edita los archivos fuente de un sub-agente directamente."""
    agent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sub_agents", agent_name)
    if not os.path.exists(agent_dir) or not os.path.isdir(agent_dir):
        raise HTTPException(status_code=404, detail="El sub-agente no existe o no es una carpeta.")
        
    py_path = os.path.join(agent_dir, f"{agent_name}_agent.py")
    mem_dir = os.path.join(agent_dir, "memoria")
    ep_path = os.path.join(mem_dir, "memoria_episodica.md")
    pr_path = os.path.join(mem_dir, "memoria_procedimental.md")
    prefs_path = os.path.join(mem_dir, "usuarios_preferencias.md")
    env_path = os.path.join(agent_dir, ".env")
    
    try:
        os.makedirs(mem_dir, exist_ok=True)
        if req.python_code is not None:
            with open(py_path, "w", encoding="utf-8") as f: f.write(req.python_code)
        if req.episodic_code is not None:
            with open(ep_path, "w", encoding="utf-8") as f: f.write(req.episodic_code)
        if req.procedural_code is not None:
            with open(pr_path, "w", encoding="utf-8") as f: f.write(req.procedural_code)
        if req.prefs_code is not None:
            with open(prefs_path, "w", encoding="utf-8") as f: f.write(req.prefs_code)
        if req.env_code is not None:
            with open(env_path, "w", encoding="utf-8") as f: f.write(req.env_code)
            
        import sys
        # Forzar descarga del modulo para que el reload tome el codigo nuevo
        mod_name = f"agent_core.sub_agents.{agent_name}.{agent_name}_agent"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        # Disparar hot-reload del grafo via la instancia global del agente
        try:
            _global_agent = request.app.state.agent
            _global_agent._sub_agents_snapshot = frozenset()  # Invalidar snapshot
            _global_agent._check_and_reload_graph()
        except Exception as reload_err:
            print(f"[hot-reload] Advertencia: {reload_err}")

        return {"status": "success", "message": "Agente editado y grafo recargado."}  
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error editando agente: {e}")

class AgentFileNode(BaseModel):
    path: str
    content: str

class AgentTreeUpdateRequest(BaseModel):
    files: list[AgentFileNode]
    deleted_paths: list[str] = []

@router.get("/agents/{agent_name}/tree")
async def get_agent_tree(agent_name: str):
    """Retorna un arbol plano con todos los archivos de un agente y su contenido."""
    agent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sub_agents", agent_name)
    if not os.path.exists(agent_dir) or not os.path.isdir(agent_dir):
        raise HTTPException(status_code=404, detail="El sub-agente no existe")
        
    result = []
    for root, dirs, files in os.walk(agent_dir):
        for file in files:
            if file == ".DS_Store" or file.endswith(".pyc") or "__pycache__" in root: continue
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, agent_dir)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                result.append({"path": rel_path, "content": content})
            except Exception:
                pass # Skip binary or unreadable files
    return result

@router.put("/agents/{agent_name}/tree")
async def update_agent_tree(agent_name: str, req: AgentTreeUpdateRequest, request: Request):
    """Guarda (o elimina) múltiples archivos de un agente usando su ruta relativa."""
    agent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sub_agents", agent_name)
    if not os.path.exists(agent_dir) or not os.path.isdir(agent_dir):
        raise HTTPException(status_code=404, detail="El sub-agente no existe")
        
    try:
        # 1. Eliminar archivos solicitados
        for dpath in req.deleted_paths:
            full_path = os.path.abspath(os.path.join(agent_dir, dpath))
            if full_path.startswith(os.path.abspath(agent_dir)) and os.path.exists(full_path):
                os.remove(full_path)
        
        # 2. Guardar/sobreescribir archivos nuevos o modificados
        for fnode in req.files:
            full_path = os.path.abspath(os.path.join(agent_dir, fnode.path))
            if not full_path.startswith(os.path.abspath(agent_dir)):
                continue
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(fnode.content)

        import sys
        # Forzar descarga del modulo para que el reload tome el codigo nuevo
        mod_name = f"agent_core.sub_agents.{agent_name}.{agent_name}_agent"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        # Disparar hot-reload del grafo via la instancia global del agente
        try:
            _global_agent = request.app.state.agent
            _global_agent._sub_agents_snapshot = frozenset()  # Invalidar snapshot
            _global_agent._check_and_reload_graph()
        except Exception as reload_err:
            print(f"[hot-reload] Advertencia: {reload_err}")

        return {"status": "success", "message": "Archivos actualizados y grafo recargado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_config():
    """Devuelve las variables de entorno configuradas directamente."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    from dotenv import dotenv_values
    config = dotenv_values(env_path)
    return config

@router.get("/ollama/tags")
async def get_ollama_tags():
    """Consulta la API local de Ollama para listar los modelos instalados."""
    try:
        import urllib.request
        import json
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        from dotenv import dotenv_values
        config = dotenv_values(env_path)
        base_url = config.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                models = [m.get("name") for m in data.get("models", [])]
                return {"models": models}
        return {"models": []}
    except Exception as e:
        print(f"[Ollama] Error al obtener tags: {e}")
        return {"models": [], "error": str(e)}

@router.get("/gemini/models")
async def get_gemini_models():
    """Consulta la API de Google para listar los modelos Gemini disponibles."""
    try:
        import urllib.request
        import json
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        from dotenv import dotenv_values
        config = dotenv_values(env_path)
        api_key = config.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        
        if not api_key:
            return {"models": [], "error": "GOOGLE_API_KEY no configurada"}
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                models = []
                for m in data.get("models", []):
                    # Solo modelos que soporten generateContent (chat/completions)
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        name = m.get("name", "").replace("models/", "")
                        display = m.get("displayName", name)
                        models.append({"name": name, "displayName": display})
                return {"models": models}
        return {"models": []}
    except Exception as e:
        print(f"[Gemini] Error al obtener modelos: {e}")
        return {"models": [], "error": str(e)}

@router.get("/anthropic/models")
async def get_anthropic_models():
    """Consulta la API de Anthropic para listar los modelos disponibles."""
    try:
        import urllib.request
        import json
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        from dotenv import dotenv_values
        config = dotenv_values(env_path)
        api_key = config.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        
        if not api_key:
            return {"models": [], "error": "ANTHROPIC_API_KEY no configurada"}
        
        url = "https://api.anthropic.com/v1/models"
        req = urllib.request.Request(url)
        req.add_header("x-api-key", api_key)
        req.add_header("anthropic-version", "2023-06-01")
        with urllib.request.urlopen(req, timeout=10.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                models = []
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    display = m.get("display_name", model_id)
                    models.append({"name": model_id, "displayName": display})
                return {"models": models}
        return {"models": []}
    except Exception as e:
        print(f"[Anthropic] Error al obtener modelos: {e}")
        return {"models": [], "error": str(e)}

@router.get("/openai/models")
async def get_openai_models():
    """Consulta la API de OpenAI para listar los modelos disponibles."""
    try:
        import urllib.request
        import json
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        from dotenv import dotenv_values
        config = dotenv_values(env_path)
        api_key = config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        
        if not api_key:
            return {"models": [], "error": "OPENAI_API_KEY no configurada"}
        
        url = "https://api.openai.com/v1/models"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=10.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                models = []
                # Filtrar solo modelos de chat (gpt, o1, o3, o4)
                chat_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt")
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if any(model_id.startswith(p) for p in chat_prefixes):
                        models.append({"name": model_id, "displayName": model_id})
                # Ordenar: modelos más recientes primero
                models.sort(key=lambda x: x["name"], reverse=True)
                return {"models": models}
        return {"models": []}
    except Exception as e:
        print(f"[OpenAI] Error al obtener modelos: {e}")
        return {"models": [], "error": str(e)}

@router.post("/config")
async def update_config(req: ConfigUpdateRequest, request: Request):
    """Actualiza una variable de entorno en el archivo .env."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
        
        with open(env_path, "w") as f:
            for line in lines:
                if line.strip().startswith(f"{req.key}="):
                    f.write(f"{req.key}={req.value}\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                if lines and not lines[-1].endswith("\n"):
                    f.write("\n")
                f.write(f"{req.key}={req.value}\n")
    else:
        with open(env_path, "w") as f:
            f.write(f"{req.key}={req.value}\n")
            
    # Hot-reload: inyectar en os.environ del proceso Python actual
    from dotenv import load_dotenv
    os.environ[req.key] = req.value
    load_dotenv(env_path, override=True)
    
    # Si la variable es crítica para el agente (API keys, modelos), re-inicializar
    CRITICAL_PREFIXES = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "MODEL_", "TZ")
    needs_reinit = any(req.key.startswith(p) for p in CRITICAL_PREFIXES)
    
    if needs_reinit:
        agent = request.app.state.agent
        if agent:
            try:
                from main import get_llm_instance
                # Tomar modelo principal default si se modificó
                main_model = os.environ.get("MODEL_PROVIDER", "gemini-2.5-flash")
                agent.llm = get_llm_instance(model_name=main_model, temperature=0.2)
                await agent.initialize()
                print(f"  [Hot-Reload] Variable crítica '{req.key}' actualizada. Agente re-inicializado.")
            except Exception as e:
                print(f"  [Hot-Reload] Advertencia al re-inicializar agente tras cambio de '{req.key}': {e}")
            
    return {"status": "ok", "message": f"Variable {req.key} actualizada.", "reinit": needs_reinit}

@router.post("/chat")
async def chat(req: MessageRequest, request: Request):
    """Procesar mensaje desde la GUI."""
    agent = request.app.state.agent
    if not agent:
        raise HTTPException(status_code=503, detail="Agente no inicializado")
        
    # Check monthly quota
    from utils.token_tracker import check_budget_exceeded
    is_exceeded, alert_msg = check_budget_exceeded()
    if is_exceeded:
        # Usamos markdown/tags adecuados para el HTML si se prefiere, aunque el GUI parsea bien
        return {
            "response": alert_msg,
            "usage": {}
        }
    
    response, usage = await agent.process_message(req.message, thread_id=req.thread_id, return_usage=True)
    return {"response": response, "usage": usage}

@router.get("/status/stream")
async def status_stream(request: Request):
    """
    SSE endpoint: emite eventos de estado del agente en tiempo real.
    El cliente se conecta al enviar un mensaje y recibe actualizaciones
    hasta que la conexión se cierra.
    """
    q = status_bus.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Esperar máximo 30 segundos por un nuevo mensaje
                    message = await asyncio.wait_for(q.get(), timeout=30.0)
                    # Formato SSE: "data: ...\n\n"
                    yield f"data: {json.dumps({'status': message})}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat para mantener la conexión viva
                    yield f"data: {json.dumps({'heartbeat': True})}\n\n"
        finally:
            status_bus.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Desactiva buffer en Nginx
            "Connection": "keep-alive",
        }
    )

@router.post("/chat/stream")
async def chat_stream(req: MessageRequest, request: Request):
    """
    SSE endpoint unificado: emite status + tokens de la respuesta en tiempo real.
    Reemplaza GET /api/status/stream + POST /api/chat para el GUI.
    
    Tipos de eventos emitidos:
      {"type": "status",  "content": "🧠 Supervisor analizando..."}
      {"type": "token",   "content": "trozo de texto..."}
      {"type": "done",    "content": "texto completo", "usage": {...}}
      {"type": "error",   "content": "mensaje de error"}
    """
    agent = request.app.state.agent
    if not agent:
        async def err_gen():
            yield f"data: {json.dumps({'type': 'error', 'content': 'Agente no inicializado'})}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    # Verificar presupuesto mensual
    from utils.token_tracker import check_budget_exceeded
    is_exceeded, alert_msg = check_budget_exceeded()
    if is_exceeded:
        async def budget_gen():
            yield f"data: {json.dumps({'type': 'done', 'content': alert_msg, 'usage': {}})}\n\n"
        return StreamingResponse(budget_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def event_generator():
        try:
            async for event in agent.stream_message(req.message, thread_id=req.thread_id):
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

@router.get("/usage")
async def get_usage_history_endpoint():
    """Devuelve el historial de uso de tokens y costos desde SQLite."""
    try:
        from utils.token_tracker import get_usage_history
        return get_usage_history(limit=1000)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo historial: {e}")

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Sube un archivo temporalmente para que el agente pueda leerlo."""
    try:
        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        # Limpiar el nombre de archivo básico (reemplazando espacios para no romper rutas locales visualmente en logs)
        safe_filename = file.filename.replace(" ", "_").replace("/", "-")
        file_path = os.path.join(uploads_dir, safe_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"[Upload] Archivo subido localmente: {file_path}")
        return {"status": "ok", "filepath": file_path, "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/config/telegram/reload")
async def reload_telegram_endpoint():
    """Fuerza la recarga del webhook de Telegram."""
    try:
        from telegram_bot import reload_telegram_bot
        res = await reload_telegram_bot()
        if res != "ok":
            raise HTTPException(status_code=500, detail=f"Fallo al conectar con Telegram: {res}")
        return {"status": "ok", "message": "¡Webhook de Telegram reconectado y verificado con éxito!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallo al recargar: {str(e)}")

@router.get("/config/telegram/status")
async def get_telegram_status():
    """Retorna si el bot de telegram está actualmente inicializado en backend."""
    from telegram_bot import bot
    if bot:
        return {"connected": True}
    return {"connected": False}

@router.get("/auth/google/status")
async def google_auth_status():
    """Estado conceptual del SSO de Google."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    from dotenv import dotenv_values
    config = dotenv_values(env_path)
    client_id = config.get("GOOGLE_CLIENT_ID", "")
    
    # Check if token.pickle exists
    keys_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
    pickle_path = os.path.join(keys_dir, "token.pickle")
    workspace_connected = os.path.exists(pickle_path)
    
    # Extraer el nombre de usuario de las preferencias si existe
    user_name = "Administrador"
    import re
    prefs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria", "episodica", "usuario_preferencias.md")
    if workspace_connected and os.path.exists(prefs_path):
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r"- Nombre real de la cuenta de usuario:\s*(.+)", content)
            if match:
                user_name = match.group(1).strip()
        except:
            pass

    return {
        "authenticated": workspace_connected,
        "message": "SSO de Google Activo" if workspace_connected else "Listo para SSO",
        "clientId": client_id,
        "workspaceConnected": workspace_connected,
        "user": {
            "name": user_name,
            "email": "Conectado vía backend (token.pickle)"
        } if workspace_connected else None
    }

@router.delete("/auth/google/revoke")
async def revoke_google_workspace():
    """Elimina el archivo token.pickle para revocar el acceso de Workspace desde el backend."""
    keys_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
    pickle_path = os.path.join(keys_dir, "token.pickle")
    
    if os.path.exists(pickle_path):
        try:
            os.remove(pickle_path)
            return {"status": "ok", "message": "Acceso revocado y token.pickle eliminado."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"No se pudo eliminar el token: {str(e)}")
    return {"status": "ok", "message": "No había token presente."}
class GoogleAuthCode(BaseModel):
    code: str

@router.post("/auth/google/exchange")
async def exchange_google_code(req: GoogleAuthCode):
    """Intercambia el auth code del frontend por un token.pickle de backend."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    from dotenv import dotenv_values
    config = dotenv_values(env_path)
    client_id = config.get("GOOGLE_CLIENT_ID", "")
    client_secret = config.get("GOOGLE_CLIENT_SECRET", "")
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Faltan credenciales de Google (CLIENT_ID o CLIENT_SECRET) en el .env")
        
    client_config = {
        "web": {
            "client_id": client_id,
            "project_id": "self-agent",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost:8080", "http://localhost:4200", "http://127.0.0.1:8080"]
        }
    }
    
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            client_config,
            scopes=[
                'https://www.googleapis.com/auth/gmail.modify',
                'https://www.googleapis.com/auth/calendar',
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/chat.spaces.readonly',
                'https://www.googleapis.com/auth/chat.messages.readonly',
                'https://www.googleapis.com/auth/chat.messages',
                'https://www.googleapis.com/auth/documents.readonly',
                'https://www.googleapis.com/auth/drive.readonly'
            ],
            redirect_uri='postmessage'
        )
        
        # Evita que oauthlib tenga un CRASH si Google devuelve scopes históricos extras
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        flow.fetch_token(code=req.code)
        credentials = flow.credentials
        
        # Guardar como token.pickle
        import pickle
        keys_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
        os.makedirs(keys_dir, exist_ok=True)
        pickle_path = os.path.join(keys_dir, "token.pickle")
        
        with open(pickle_path, "wb") as token_file:
            pickle.dump(credentials, token_file)
            
        return {"status": "ok", "message": "Token de Workspace generado y guardado exitosamente en el backend."}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al generar token: {str(e)}")

# --- TASKS / REMINDERS API ---

@router.get("/tasks")
async def get_tasks():
    """Obtiene la lista de tareas programadas desde SQLite."""
    try:
        tasks = get_all_jobs()
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo tareas: {e}")

@router.post("/tasks")
async def create_task(req: TaskCreateRequest):
    """Crea una nueva tarea programada."""
    try:
        if req.type == "date":
            # Validar fecha
            run_date = datetime.fromisoformat(req.value)
            func_to_call = execute_agent_task if req.is_agent_action else send_telegram_reminder
            scheduler.add_job(
                func_to_call,
                'date',
                run_date=run_date,
                args=[req.chat_id, req.message_or_prompt],
                name=req.message_or_prompt[:50]
            )
        elif req.type == "interval":
            # Validar minutos
            minutes = float(req.value)
            func_to_call = execute_agent_task if req.is_agent_action else send_dynamic_telegram_reminder
            scheduler.add_job(
                func_to_call,
                'interval',
                minutes=minutes,
                args=[req.chat_id, req.message_or_prompt],
                name=f"Rutina: {req.message_or_prompt[:30]}"
            )
        elif req.type == "cron":
            # Validar HH:MM
            h, m = req.value.split(":")
            func_to_call = execute_agent_task if req.is_agent_action else send_dynamic_telegram_reminder
            scheduler.add_job(
                func_to_call,
                'cron',
                hour=int(h),
                minute=int(m),
                args=[req.chat_id, req.message_or_prompt],
                name=f"Rutina Dia: {req.message_or_prompt[:30]}"
            )
        elif req.type == "cron_expr":
            from apscheduler.triggers.cron import CronTrigger
            func_to_call = execute_agent_task if req.is_agent_action else send_dynamic_telegram_reminder
            trigger = CronTrigger.from_crontab(req.value)
            scheduler.add_job(
                func_to_call,
                trigger=trigger,
                args=[req.chat_id, req.message_or_prompt],
                name=f"Rutina Avanzada: {req.message_or_prompt[:30]}"
            )
        else:
            raise HTTPException(status_code=400, detail="Tipo de tarea inválido. Use 'date', 'interval', 'cron' o 'cron_expr'.")
        
        guardar_estado_jobs()
        return {"status": "ok", "message": "Tarea programada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Elimina una tarea programada."""
    try:
        scheduler.remove_job(task_id)
        guardar_estado_jobs()
        return {"status": "ok", "message": f"Tarea {task_id} eliminada."}
    except Exception as e:
        # Si no existe APScheduler lanza una excepción
        raise HTTPException(status_code=404, detail=f"No se pudo encontrar o eliminar la tarea: {e}")

@router.put("/tasks/{task_id}")
async def update_task_instruction(task_id: str, req: TaskUpdateRequest):
    """Actualiza la instrucción (argumento) de una tarea programada y su nombre."""
    try:
        job = scheduler.get_job(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        old_args = list(job.args)
        if len(old_args) >= 2:
            old_args[1] = req.message_or_prompt
            
            # Reflejar parte del texto en el nombre también
            is_agent = job.func.__name__ == 'execute_agent_task'
            prefix = "Rutina"
            if job.trigger.__class__.__name__ == 'CronTrigger':
                prefix = "Rutina Dia"
            if not is_agent:
                prefix = "Aviso"
            
            new_name = req.message_or_prompt[:50] if type(job.trigger).__name__ == 'DateTrigger' else f"{prefix}: {req.message_or_prompt[:30]}"
            
            scheduler.modify_job(task_id, args=tuple(old_args), name=new_name)
            guardar_estado_jobs()
            return {"status": "ok", "message": "Tarea actualizada correctamente."}
        else:
            raise HTTPException(status_code=400, detail="El formato de la tarea no es compatible para la edición.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando tarea: {e}")

# Rutas estáticas ANTES de las parameterizadas para evitar conflictos en FastAPI
@router.get("/tasks/logs/all")
async def get_all_task_execution_logs(limit: int = 200):
    """Devuelve el historial de ejecuciones de todas las tareas."""
    try:
        from utils.task_logger import get_all_task_logs
        return get_all_task_logs(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo logs: {e}")

@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str):
    """Ejecuta una tarea programada inmediatamente sin alterar su próximo horario."""
    try:
        job = scheduler.get_job(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        func = job.func
        args = list(job.args) if job.args else []
        
        async def run_in_background():
            try:
                await func(*args, _trigger_type="manual", _job_id=task_id)
            except TypeError:
                await func(*args)
        
        asyncio.create_task(run_in_background())
        return {"status": "ok", "message": f"Tarea '{job.name}' ejecutándose en background."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando tarea: {e}")

@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    """Pausa una tarea programada (no la elimina, solo detiene su ejecución)."""
    try:
        job = scheduler.get_job(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        scheduler.pause_job(task_id)
        guardar_estado_jobs()
        return {"status": "ok", "message": f"Tarea '{job.name}' pausada."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error pausando tarea: {e}")

@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """Reanuda una tarea previamente pausada."""
    try:
        job = scheduler.get_job(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        scheduler.resume_job(task_id)
        guardar_estado_jobs()
        return {"status": "ok", "message": f"Tarea '{job.name}' reanudada."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reanudando tarea: {e}")

@router.get("/tasks/{task_id}/logs")
async def get_task_execution_logs(task_id: str, limit: int = 50):
    """Devuelve el historial de ejecuciones de una tarea específica."""
    try:
        from utils.task_logger import get_task_logs
        return get_task_logs(task_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo logs: {e}")

# ==========================================
# WEBHOOKS ENDPOINTS
# ==========================================

@router.get("/webhooks")
async def api_get_webhooks():
    return load_webhooks()

@router.post("/webhooks")
async def api_create_webhook(req: WebhookCreateRequest):
    wh = create_webhook(req.titulo, req.descripcion, req.modelo)
    return {"status": "success", "webhook": wh}

@router.put("/webhooks/{webhook_id}")
async def api_update_webhook(webhook_id: str, req: WebhookUpdateRequest):
    wh = update_webhook(webhook_id, req.titulo, req.descripcion, req.modelo, req.paused)
    if wh:
        return {"status": "success", "webhook": wh}
    raise HTTPException(status_code=404, detail="Webhook no encontrado")

@router.delete("/webhooks/{webhook_id}")
async def api_delete_webhook(webhook_id: str):
    if delete_webhook(webhook_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Webhook no encontrado")

@router.get("/webhooks/{webhook_id}/logs")
async def api_get_webhook_logs(webhook_id: str):
    return get_webhook_logs(webhook_id)

@router.get("/webhooks/logs/all")
async def api_get_all_webhook_logs():
    return get_webhook_logs()

@router.post("/webhook/{webhook_id}")
async def handle_dynamic_webhook(webhook_id: str, request: Request):
    """Endpoint receptor dinámico para webhooks."""
    wh = get_webhook(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook no encontrado o inactivo")
        
    if wh.get("paused"):
        return JSONResponse(status_code=422, content={"status": "paused", "message": "Este webhook está en pausa."})
        
    try:
        # Intentar obtener payload JSON, si falla obtener texto crudo
        try:
            payload = await request.json()
        except Exception:
            try:
                payload_bytes = await request.body()
                payload = payload_bytes.decode('utf-8')
            except Exception:
                payload = "No_Payload"
                
        prompt = (
            f"El webhook local '{wh.get('titulo')}' ha recibido un payload. "
            f"INSTRUCCIONES DE SISTEMA: {wh.get('descripcion')}\n\n"
            f"PAYLOAD RECIBIDO:\n```json\n{json.dumps(payload, indent=2, ensure_ascii=False) if isinstance(payload, dict) else payload}\n```\n\n"
            f"REGLA CRUCIAL: Tu respuesta final en texto será reenviada AUTOMÁTICAMENTE por Telegram al usuario. "
            f"Por favor, NO ASUMAS que debes usar herramientas como `crear_recordatorio` para notificarlo. Limítate a cumplir las instrucciones y entregar el texto final, sabiendo que el sistema se encargará de despacharlo de inmediato a su Telegram."
        )
        
        agent = request.app.state.agent
        if agent:
            import asyncio
            import os
            
            async def process_and_notify():
                try:
                    respuesta = await agent.process_message(
                        prompt, 
                        thread_id=f"webhook_{webhook_id}"
                    )
                    
                    if not respuesta:
                        return
                        
                    # Notify via Telegram
                    from telegram import Bot
                    from telegram.constants import ParseMode
                    import re
                    
                    token = os.getenv("TELEGRAM_TOKEN")
                    chat_id = os.getenv("TELEGRAM_CHAT_ID")
                    
                    if token and chat_id:
                        bot = Bot(token=token)
                        
                        # Apply naive formatting mimicking telegram_bot.py
                        text = respuesta.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
                        text = re.sub(r'(?<!\*)\*(?!\s)(?!\*)(.*?)(?<!\s)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
                        text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
                        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
                        
                        try:
                            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
                            log_webhook_execution(webhook_id, payload, respuesta)
                        except Exception as e:
                            print(f"Error HTML telegram sender in webhook: {e}")
                            await bot.send_message(chat_id=chat_id, text=respuesta)
                            log_webhook_execution(webhook_id, payload, respuesta, error=f"HTML error: {e}")
                            
                except Exception as e:
                    print(f"Error procesando webhook background task: {e}")
                    log_webhook_execution(webhook_id, payload, "Fallo al procesar", error=str(e))

            # We run it in background to immediately return 202
            asyncio.create_task(process_and_notify())
            
        return JSONResponse(status_code=202, content={"status": "accepted", "message": "Payload recibido y enviado al agente en segundo plano."})
        
    except Exception as e:
        print(f"Error procesando webhook {webhook_id}: {e}")
        raise HTTPException(status_code=500, detail="Error interno al procesar webhook")


# --- MCP MANAGER API ---

import yaml
MCP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_config.yaml")

class McpServerConfig(BaseModel):
    name: str
    command: str = "npx"
    transport: str = "stdio"
    args: list[str] = []
    env: dict[str, str] = {}

def load_mcp_config():
    if not os.path.exists(MCP_CONFIG_PATH):
        return {"mcp_servers": []}
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if "mcp_servers" not in data:
                data["mcp_servers"] = []
            return data
    except yaml.YAMLError:
        return {"mcp_servers": []}

def save_mcp_config(data):
    lines = ["mcp_servers:"]
    for s in data.get("mcp_servers", []):
        lines.append(f'  - name: "{s.get("name", "")}"')
        lines.append(f'    command: "{s.get("command", "")}"')
        lines.append(f'    transport: "{s.get("transport", "")}"')
        
        args = s.get("args", [])
        if args:
            lines.append('    args: [')
            for i, a in enumerate(args):
                suffix = "," if i < len(args)-1 else ""
                lines.append(f'      "{a}"{suffix}')
            lines.append('    ]')
        else:
            lines.append('    args: []')
            
        env = s.get("env", {})
        if env:
            lines.append('    env:')
            for k, v in env.items():
                lines.append(f'      {k}: "{v}"')
        else:
            lines.append('    env: {}')
    
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
@router.get("/mcp")
async def get_mcp_servers():
    """Devuelve la lista de servidores MCP configurados."""
    data = load_mcp_config()
    return data.get("mcp_servers", [])

@router.post("/mcp")
async def create_mcp_server(server: McpServerConfig, request: Request):
    """Añade un nuevo servidor MCP al yaml."""
    data = load_mcp_config()
    # Evitar duplicados
    for existing in data.get("mcp_servers", []):
        if existing["name"] == server.name:
            raise HTTPException(status_code=400, detail=f"El servidor '{server.name}' ya existe.")
            
    data["mcp_servers"].append(server.dict())
    save_mcp_config(data)
    
    # Reload mcp client dynamically on backend
    agent = request.app.state.agent
    if agent and hasattr(agent, "mcp_manager"):
        import asyncio
        async def reinit():
            agent.mcp_manager.config = data
            await agent.mcp_manager.close()
            await agent.initialize()
        asyncio.create_task(reinit())
    
    return {"status": "ok", "message": f"Servidor {server.name} agregado exitosamente."}

@router.put("/mcp/{name}")
async def update_mcp_server(name: str, server: McpServerConfig, request: Request):
    """Actualiza la configuración de un MCP existente."""
    data = load_mcp_config()
    updated = False
    for i, existing in enumerate(data.get("mcp_servers", [])):
        if existing["name"] == name:
            data["mcp_servers"][i] = server.dict()
            updated = True
            break
            
    if not updated:
        raise HTTPException(status_code=404, detail="Servidor no encontrado.")
        
    save_mcp_config(data)
    
    agent = request.app.state.agent
    if agent and hasattr(agent, "mcp_manager"):
        import asyncio
        async def reinit():
            agent.mcp_manager.config = data
            await agent.mcp_manager.close()
            await agent.initialize()
        asyncio.create_task(reinit())
    
    return {"status": "ok", "message": f"Servidor {name} actualizado."}

@router.delete("/mcp/{name}")
async def delete_mcp_server(name: str, request: Request):
    """Elimina permanentemente un servidor MCP del pool."""
    data = load_mcp_config()
    initial_length = len(data.get("mcp_servers", []))
    data["mcp_servers"] = [s for s in data.get("mcp_servers", []) if s["name"] != name]
    
    if len(data["mcp_servers"]) == initial_length:
        raise HTTPException(status_code=404, detail="Servidor no encontrado.")
        
    save_mcp_config(data)
    
    agent = request.app.state.agent
    if agent and hasattr(agent, "mcp_manager"):
        import asyncio
        async def reinit():
            agent.mcp_manager.config = data
            await agent.mcp_manager.close()
            await agent.initialize()
        asyncio.create_task(reinit())
    
    return {"status": "ok", "message": f"Servidor {name} eliminado."}
