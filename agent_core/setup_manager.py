import os
import json
import secrets
from fastapi import APIRouter, HTTPException, Request as FastAPIRequest

from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import set_key
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt
import pickle
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import Flow

ph = PasswordHasher()
# Usaremos una huella en memoria o del .env
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))

# Constants
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
STATUS_PATH = os.path.join(CONFIG_DIR, "status.json")
KEY_PATH = os.path.join(CONFIG_DIR, "activation.key")
USERS_PATH = os.path.join(CONFIG_DIR, "users.json")
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
PREFS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria", "episodica", "usuario_preferencias.md")

KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys')
CREDENTIALS_PATH = os.path.join(KEYS_DIR, 'credentials.json')
TOKEN_PATH = os.path.join(KEYS_DIR, 'token.pickle')

# Google Scopes base
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/chat.spaces.readonly',
    'https://www.googleapis.com/auth/chat.messages.readonly',
    'https://www.googleapis.com/auth/chat.messages',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

setup_router = APIRouter(prefix="/api/setup")

def get_status():
    if not os.path.exists(STATUS_PATH):
        return {"setup_completed": False, "admin_created": False}
    with open(STATUS_PATH, "r") as f:
        return json.load(f)

def save_status(status_data):
    with open(STATUS_PATH, "w") as f:
        json.dump(status_data, f, indent=4)

def check_and_init_setup():
    """Initializes the config folder and generates activation key if virgin system."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # Initialize status file
    status = get_status()
    if not os.path.exists(STATUS_PATH):
        save_status(status)
        
    # Initialize user datastore
    if not os.path.exists(USERS_PATH):
        with open(USERS_PATH, "w") as f:
            json.dump([], f)
            
    # Generate activation key if admin is not created
    if not status.get("admin_created", False):
        if not os.path.exists(KEY_PATH):
            key = secrets.token_urlsafe(32)
            with open(KEY_PATH, "w") as f:
                f.write(key)
            print("=====================================================")
            print("=        SETUP REQUIRED: NEW SYSTEM DETECTED        =")
            print("=====================================================")
            print(f" Activation Key: {key}")
            print(" Provide this key in the GUI to create the Admin.")
            print("=====================================================\n")

# --- Pydantic Models for Endpoints ---

class ValidateKeyRequest(BaseModel):
    key: str

class AdminCreateRequest(BaseModel):
    key: str
    username: str
    password: str

class PreferencesRequest(BaseModel):
    user_name: str
    preferred_name: str = None
    agent_name: str
    agent_personality: str

class EnvConfigUpdateRequest(BaseModel):
    configs: dict

class LoginRequest(BaseModel):
    username: str
    password: str

# --- Endpoints ---

@setup_router.get("/status")
async def setup_status():
    return get_status()

@setup_router.post("/validate-key")
async def validate_key(req: ValidateKeyRequest):
    status = get_status()
    if status.get("admin_created"):
        return {"valid": False, "message": "Admin already created."}
        
    if not os.path.exists(KEY_PATH):
        return {"valid": False, "message": "Activation key file missing in backend."}
        
    with open(KEY_PATH, "r") as f:
        real_key = f.read().strip()
        
    if req.key == real_key:
        return {"valid": True, "message": "Key valid. Proceed to create admin."}
    return {"valid": False, "message": "Invalid key."}

@setup_router.post("/admin")
async def create_admin(req: AdminCreateRequest):
    status = get_status()
        
    # Validamos siempre con la llave en disco. Si no existe, es que ya termino el setup.
    if not os.path.exists(KEY_PATH):
        raise HTTPException(status_code=401, detail="La llave de activación ya no es válida o el Setup fue finalizado.")

    with open(KEY_PATH, "r") as f:
        real_key = f.read().strip()
    if req.key != real_key:
        raise HTTPException(status_code=401, detail="Invalid activation key.")
        
    user_data = {
        "username": req.username,
        "password": ph.hash(req.password),
        "role": "admin"
    }
    
    users = []
    if os.path.exists(USERS_PATH):
        with open(USERS_PATH, "r") as f:
            try:
                users = json.load(f)
            except json.JSONDecodeError:
                users = []
            
    # Si el usuario presiona "Back" y vuelve a grabar, purgamos amigablemente su old-admin y volcamos el nuevo
    users = [u for u in users if u.get("role") != "admin"]
    users.insert(0, user_data)
    
    with open(USERS_PATH, "w") as f:
        json.dump(users, f, indent=4)
        
    # Nota: Ya NO borramos la KEY aquí para permitirle al usuario usar el botón back impunemente
        
    return {"status": "ok", "message": "Administrador engranado temporalmente."}

@setup_router.post("/login")
async def login(req: LoginRequest):
    if not os.path.exists(USERS_PATH):
        raise HTTPException(status_code=401, detail="Usuario no encontrado.")
        
    with open(USERS_PATH, "r") as f:
        users = json.load(f)
        
    for user in users:
        if user["username"] == req.username:
            try:
                # Argon2 Verify
                ph.verify(user["password"], req.password)
                
                # Update hash if Argon2 parameters changed in the future
                if ph.check_needs_rehash(user["password"]):
                    pass # We skip auto-rehashing for simplicity here
                    
                # Generate JWT
                expire = datetime.utcnow() + timedelta(days=7)
                token_data = {"sub": req.username, "role": user.get("role", "admin"), "exp": expire}
                token = jwt.encode(token_data, JWT_SECRET, algorithm="HS256")
                
                return {"status": "ok", "token": token, "username": req.username, "role": user.get("role", "admin")}
            except VerifyMismatchError:
                raise HTTPException(status_code=401, detail="Contraseña o usuario incorrectos.")
                
    raise HTTPException(status_code=401, detail="Contraseña o usuario incorrectos.")

@setup_router.post("/config-batch")
async def update_env_batch(req: EnvConfigUpdateRequest):
    """Guarda múltiples configuraciones en el .env a la vez."""
    # To use set_key from dotenv properly
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, 'a').close()
        
    for key, value in req.configs.items():
        set_key(ENV_PATH, key, value)
        os.environ[key] = value # Hot-reload dict in memory

    return {"status": "ok", "message": "Configuración guardada en el backend."}

@setup_router.post("/preferences")
async def save_preferences(req: PreferencesRequest, request: FastAPIRequest):
    """Guarda las preferencias del usuario (memoria) y marca el setup como completado."""
    apodo_regla = f"\n- Apodo o nombre principal de trato: El usuario indicó que SIEMPRE debes llamarle o referirte a él/ella exclusivamente como: '{req.preferred_name}'" if req.preferred_name else ""
    content = f"# Identidad y Preferencias Maestras\n\n- Nombre real de la cuenta de usuario: {req.user_name}{apodo_regla}\n- Nombre que le diste al agente: {req.agent_name}\n\n## Personalidad y Foco\n{req.agent_personality}\n\n*Nota del sistema: El agente debe internalizar este rol, temperamento y contexto en TODAS las respuestas futuras.*\n"
    
    os.makedirs(os.path.dirname(PREFS_PATH), exist_ok=True)
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Recien aquí destruimos la llave de oro, sellando las puertas del backend para siempre.
    if os.path.exists(KEY_PATH):
        os.remove(KEY_PATH)
        
    # Mark setup as completed
    status = get_status()
    status["setup_completed"] = True
    status["admin_created"] = True
    save_status(status)
    
    # Auto-inicializar el agente después de completar el setup
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)
        
        agent = request.app.state.agent
        if agent and not getattr(request.app.state, 'agent_ready', False):
            print("\\n🚀 Setup completado. Inicializando agente automáticamente...")
            await agent.initialize()
            request.app.state.agent_ready = True
            print("✅ Agente inicializado correctamente tras el setup.\\n")
            
        # Refrescar silenciosamente el webhook/bot de telegram
        try:
            from agent_core.telegram_bot import reload_telegram_bot
            await reload_telegram_bot()
        except Exception as e:
            print(f"⚠️  Aviso: falló recarga del telegram bot en on-the-fly -> {e}")
            
    except Exception as e:
        print(f"⚠️  No se pudo inicializar el agente tras el setup: {e}")
        print("⚠️  Reinicia el contenedor manualmente para completar la inicialización.\\n")
    
    return {"status": "ok", "message": "Memorias guardadas. Setup erradicado con éxito."}

class GoogleAuthRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str

@setup_router.post("/google-auth-url")
async def get_google_auth_url(req: GoogleAuthRequest):
    os.makedirs(KEYS_DIR, exist_ok=True)
    creds_data = {
        "installed": {
            "client_id": req.client_id,
            "project_id": "leygo-agent",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": req.client_secret,
            "redirect_uris": [req.redirect_uri, "http://localhost:8080"]
        }
    }
    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(creds_data, f, indent=4)
        
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_PATH,
        scopes=SCOPES,
        redirect_uri=req.redirect_uri
    )
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
    
    # Parche PKCE: Guardamos efimeramente state y code_verifier para la llegada del callback
    auth_state_path = os.path.join(KEYS_DIR, "auth_state.json")
    with open(auth_state_path, "w") as f:
        json.dump({"state": state, "code_verifier": flow.code_verifier}, f)
        
    return {"status": "ok", "url": auth_url}

@setup_router.get("/google-callback")
async def google_callback(code: str, state: str = None):
    if not os.path.exists(CREDENTIALS_PATH):
        return HTMLResponse("<html><body>Error crítico: credentials.json no existe en el backend. Cierra y vuelve a intentar.</body></html>")
    
    try:
        # Leemos el redirect_uri dinámico que guardamos en credentials.json para que haga match 100% exacto
        with open(CREDENTIALS_PATH, "r") as f:
            creds_data = json.load(f)
            redirect_uri_base = creds_data.get("installed", {}).get("redirect_uris", [""])[0]
        # Recuperamos la firma PKCE temporal
        auth_state_path = os.path.join(KEYS_DIR, "auth_state.json")
        saved_state = state
        code_verifier = None
        if os.path.exists(auth_state_path):
            with open(auth_state_path, "r") as f:
                state_data = json.load(f)
                saved_state = state_data.get("state", state)
                code_verifier = state_data.get("code_verifier")
        
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=SCOPES,
            state=saved_state,
            redirect_uri=redirect_uri_base
        )
        
        # Le inyectamos manualmente la firma recordada para satisfacer a Google
        if code_verifier:
            # En la versión de auth-oauthlib, el fetch token en la request original buscará la propiedad kwargs o de memoria interna.
            flow.fetch_token(code=code, code_verifier=code_verifier)
        else:
            flow.fetch_token(code=code)
        
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(flow.credentials, f)
            
        # Purgamos la memoria efímera
        if os.path.exists(auth_state_path):
            os.remove(auth_state_path)
            
        return HTMLResponse("""
        <html>
            <body style="background:#f9fafb; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; font-family:sans-serif; color:#111827;">
                <div style="background:white; padding:40px; border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.1); text-align:center;">
                    <h1 style="color:#10b981; margin-top:0;">¡Felicidades!</h1>
                    <p style="font-size:1.1rem">Tu cuenta de Google fue vinculada con éxito.</p>
                    <p style="color:#6b7280;"><b>token.pickle</b> fue generado a baja profundidad en el servidor.</p>
                    <p style="margin-top:20px;">Puedes cerrar esta pestaña o la ventana emergente tranquilamente y continuar el Setup.</p>
                    <button onclick="window.close()" style="margin-top:20px; padding:10px 20px; background:#6366f1; color:white; border:none; border-radius:6px; cursor:pointer;">Cerrar Ventana</button>
                    <script>setTimeout(()=>window.close(), 4000);</script>
                </div>
            </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<html><body><h2>Error con Google OAuth</h2><p>{str(e)}</p></body></html>")
