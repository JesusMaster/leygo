from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import sys
from dotenv import dotenv_values

# Añadir el path para importar el agente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import discover_sub_agents

router = APIRouter(prefix="/api")

class MessageRequest(BaseModel):
    message: str
    thread_id: str = "gui_session"

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str

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
    """Devuelve las variables de entorno configuradas (sensibles ocultas)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    config = dotenv_values(env_path)
    # Enmascarar valores sensibles
    masked_config = {}
    sensibles = ["GOOGLE_API_KEY", "TELEGRAM_TOKEN", "GITHUB_TOKEN", "BEARER_TOKEN"]
    for k, v in config.items():
        if k in sensibles and v:
            masked_config[k] = f"{v[:4]}...{v[-4:]}"
        else:
            masked_config[k] = v
    return masked_config

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
                f.write(f"{req.key}={req.value}\n")
    else:
        with open(env_path, "w") as f:
            f.write(f"{req.key}={req.value}\n")
            
    return {"status": "ok", "message": f"Variable {req.key} actualizada."}

@router.post("/chat")
async def chat(req: MessageRequest, request: Request):
    """Procesar mensaje desde la GUI."""
    agent = request.app.state.agent
    if not agent:
        raise HTTPException(status_code=503, detail="Agente no inicializado")
    
    response = await agent.process_message(req.message, thread_id=req.thread_id)
    return {"response": response}

@router.get("/auth/google/status")
async def google_auth_status():
    """Estado conceptual del SSO de Google."""
    return {
        "authenticated": False,
        "message": "SSO de Google no configurado aún en el backend."
    }
