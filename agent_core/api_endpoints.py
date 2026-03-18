from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import sys
from dotenv import dotenv_values

# Añadir el path para importar el agente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import discover_sub_agents
from scheduler_manager import scheduler, MEMORIA_RECORDATORIOS_PATH, guardar_estado_jobs, send_telegram_reminder, send_dynamic_telegram_reminder, execute_agent_task
import json
from datetime import datetime

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
    
    response, usage = await agent.process_message(req.message, thread_id=req.thread_id, return_usage=True)
    return {"response": response, "usage": usage}

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
    
    return {
        "authenticated": False,
        "message": "Listo para SSO" if client_id else "SSO de Google no configurado aún en el backend.",
        "clientId": client_id,
        "workspaceConnected": workspace_connected
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
                'https://www.googleapis.com/auth/chat.messages'
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
