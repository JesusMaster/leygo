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
from scheduler_manager import scheduler, MEMORIA_RECORDATORIOS_PATH, guardar_estado_jobs, send_telegram_reminder, send_dynamic_telegram_reminder, execute_agent_task
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
                    tools_list.append({
                        "name": getattr(t, "name", t.__name__),
                        "description": getattr(t, "description", t.__doc__ or "Sin descripción")
                    })
            except:
                pass

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

@router.get("/config")
async def get_config():
    """Devuelve las variables de entorno configuradas directamente."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    from dotenv import dotenv_values
    config = dotenv_values(env_path)
    return config

@router.post("/config")
async def update_config(req: ConfigUpdateRequest):
    """Actualiza una variable de entorno en el archivo .env."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    # Nota: En un entorno real usaríamos una librería más robusta para editar .env
    # Por ahora lo haremos de forma simple
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
            
    # Hot-reload inyectando en las variables de entorno actuales python (al vuelo)
    from dotenv import load_dotenv
    os.environ[req.key] = req.value
    load_dotenv(env_path, override=True)
            
    return {"status": "ok", "message": f"Variable {req.key} actualizada."}

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
async def get_usage_history():
    """Devuelve el historial de uso de tokens y costos."""
    history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria", "usage_history.json")
    if not os.path.exists(history_path):
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history
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
    """Obtiene la lista de tareas programadas desde el archivo JSON."""
    if not os.path.exists(MEMORIA_RECORDATORIOS_PATH):
        return []
    try:
        with open(MEMORIA_RECORDATORIOS_PATH, "r", encoding="utf-8") as f:
            tasks = json.load(f)
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
        else:
            raise HTTPException(status_code=400, detail="Tipo de tarea inválido. Use 'date', 'interval' o 'cron'.")
        
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
        asyncio.create_task(agent.mcp_manager.reload_all(new_config=data))
    
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
        asyncio.create_task(agent.mcp_manager.reload_all(new_config=data))
    
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
        asyncio.create_task(agent.mcp_manager.reload_all(new_config=data))
    
    return {"status": "ok", "message": f"Servidor {name} eliminado."}
