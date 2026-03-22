import os
import json
import yaml
from langchain_core.tools import tool
from dotenv import load_dotenv, set_key
from google_auth import get_google_credentials

# Base directory is one level up from this file's location (assuming memory_utils.py is in agent_core)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_CORE_DIR = os.path.join(BASE_DIR, "agent_core")
MEMORY_DIR = os.path.join(AGENT_CORE_DIR, "memoria")
EPISODICA_DIR = os.path.join(MEMORY_DIR, "episodica")
PROCEDIMENTAL_DIR = os.path.join(MEMORY_DIR, "procedimental")
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")

# Limitar el tamaño de memoria cargada para evitar inflar tokens
MAX_MEMORY_FILE_CHARS = 2000  # máximo por archivo
MAX_MEMORY_TOTAL_CHARS = 4000  # máximo total combinado

def init_memory_structure():
    """Initializes the memory folder structure if it doesn't exist."""
    directories = [
        AGENT_CORE_DIR,
        MEMORY_DIR,
        EPISODICA_DIR,
        PROCEDIMENTAL_DIR,
        SANDBOX_DIR
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    print("Memoria inicializada.")

def save_mcp_config(config: dict):
    """Saves the MCP server configuration back to mcp_config.yaml."""
    file_path = os.path.join(AGENT_CORE_DIR, "mcp_config.yaml")
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

def load_mcp_config() -> dict:
    """Loads the MCP server configuration from mcp_config.yaml."""
    file_path = os.path.join(AGENT_CORE_DIR, "mcp_config.yaml")
    if not os.path.exists(file_path):
        return {"mcp_servers": []}
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {"mcp_servers": []}

def save_episodic_memory(filename: str, content: str):
    """Saves episodic context (e.g. user preferences, project context) as .md."""
    if not filename.endswith('.md'):
        filename += '.md'
    file_path = os.path.join(EPISODICA_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def read_episodic_memory(filename: str) -> str:
    """Reads episodic context."""
    if not filename.endswith('.md'):
        filename += '.md'
    file_path = os.path.join(EPISODICA_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def save_procedural_memory(filename: str, content: str):
    """Saves procedural code/docs (e.g. python skill files or docs)."""
    file_path = os.path.join(PROCEDIMENTAL_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def read_procedural_memory(filename: str) -> str:
    """Reads procedural code/docs from memory."""
    file_path = os.path.join(PROCEDIMENTAL_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def list_procedural_skills():
    """Returns a list of base filenames in procedural memory."""
    if os.path.exists(PROCEDIMENTAL_DIR):
        return os.listdir(PROCEDIMENTAL_DIR)
    return []

def check_and_run_setup_wizard():
    """Checks if user profile exists; if not, runs a setup wizard in terminal."""
    preferences_file = os.path.join(EPISODICA_DIR, "usuario_preferencias.md")
    
    if os.path.exists(preferences_file):
        return

    print("=========================================================")
    print("🤖 ¡Bienvenido al proyecto ly!")
    print("Parece que es nuestra primera vez hablando.")
    print("Vamos a conocernos un poco para personalizar tu experiencia.")
    print("=========================================================\n")
    
    try:
        user_name = input("¿Cómo te gusta que te llamen? ").strip()
        bot_name = input("¿Qué nombre te gustaría ponerme a mí (el IA)? ").strip()
    except EOFError:
        user_name = "Usuario"
        bot_name = "Leygo"
    
    print("\n¡Gracias! Creando perfil de memoria semántica inicial...\n")
    
    contextual_profile = f"""
# Preferencias del Usuario
- El nombre del usuario es: {user_name}
- El nombre asignado a este asistente IA es: {bot_name}
- Al usuario le gusta que las respuestas sean concisas y directas.
"""
    save_episodic_memory("usuario_preferencias.md", contextual_profile.strip())
    
def check_and_run_env_wizard():
    """Checks if GOOGLE_API_KEY is configured in .env; if not, asks for it."""
    env_file = os.path.join(AGENT_CORE_DIR, ".env")
    
    # Asegúrate de cargar las variables de entorno actuales 
    load_dotenv(env_file)
    
    # Comprobar si hay una API Key de Gemini
    if not os.getenv("GOOGLE_API_KEY"):
        print("\n=========================================================")
        print("🔑 FALTAN CLAVES DE ACCESO (API KEYS)")
        print("El agente usa los modelos de Gemini para su razonamiento.")
        print("Puedes obtener una API Key gratuita en: https://aistudio.google.com/")
        print("=========================================================\n")
        
        try:
            google_api_key = input("Pega aquí tu GOOGLE_API_KEY (o presiona Enter para omitir): ").strip()
        except EOFError:
            google_api_key = ""
        
        if google_api_key:
            if not os.path.exists(env_file):
                with open(env_file, 'w', encoding='utf-8') as f:
                    pass
            set_key(env_file, "GOOGLE_API_KEY", google_api_key)
            os.environ["GOOGLE_API_KEY"] = google_api_key
            print("=> API Key guardada exitosamente en agent_core/.env\n")
        else:
            print("=> Advertencia: Arrancando el agente sin LLM. Muchas funciones fallarán.\n")

    # Comprobar si hay credenciales de Telegram
    if not os.getenv("TELEGRAM_TOKEN"):
        print("\n=========================================================")
        print("📱 CONFIGURACIÓN DE TELEGRAM (Opcional)")
        print("=========================================================\n")
        try:
            resp = input("¿Deseas configurar el bot de Telegram ahora? (s/n): ").strip().lower()
        except EOFError:
            resp = 'n'
            
        if resp == 's':
            try:
                telegram_token = input("Ingresa tu TELEGRAM_TOKEN: ").strip()
                telegram_chat_id = input("Ingresa tu TELEGRAM_CHAT_ID (opcional, presiona Enter para omitir): ").strip()
            except EOFError:
                telegram_token = ""
                telegram_chat_id = ""
            
            if telegram_token:
                if not os.path.exists(env_file):
                    with open(env_file, 'w', encoding='utf-8') as f:
                        pass
                set_key(env_file, "TELEGRAM_TOKEN", telegram_token)
                os.environ["TELEGRAM_TOKEN"] = telegram_token
                
                if telegram_chat_id:
                    set_key(env_file, "TELEGRAM_CHAT_ID", telegram_chat_id)
                    os.environ["TELEGRAM_CHAT_ID"] = telegram_chat_id
                    
                print("=> Credenciales de Telegram guardadas exitosamente en agent_core/.env\n")
            else:
                print("=> Operación cancelada. El token es obligatorio para Telegram.\n")

    # Comprobar inicio de sesión SSO en Google Workspace
    print("\n=========================================================")
    print("🌐 CONEXIÓN A GOOGLE WORKSPACE (Opcional)")
    print("=========================================================\n")
    get_google_credentials()

def load_all_episodic_context(agent_name: str = None) -> str:
    """Reads all .md files in the episodic memory directory and returns a unified context string."""
    context_blocks = []
    
    # 1. Global episodic context
    if os.path.exists(EPISODICA_DIR):
        for filename in sorted(os.listdir(EPISODICA_DIR)):
            if filename.endswith(".md"):
                content = read_episodic_memory(filename)
                if content:
                    context_blocks.append(f"--- Archivo de Contexto Global: {filename} ---\n{content}\n")
                    
    # 2. Agent-specific episodic context
    if agent_name:
        agent_episodica_dir = os.path.join(AGENT_CORE_DIR, "sub_agents", agent_name, "episodica")
        if os.path.exists(agent_episodica_dir):
            for filename in sorted(os.listdir(agent_episodica_dir)):
                if filename.endswith(".md"):
                    with open(os.path.join(agent_episodica_dir, filename), 'r', encoding='utf-8') as f:
                        context_blocks.append(f"--- Archivo de Contexto Específico del Agente ({agent_name}): {filename} ---\n{f.read()}\n")
                        
    result = "\n".join(context_blocks)
    if len(result) > MAX_MEMORY_TOTAL_CHARS:
        result = result[:MAX_MEMORY_TOTAL_CHARS] + "\n[... memoria truncada por límite de tokens]"  
    return result

def load_procedural_documentation(agent_name: str = None) -> str:
    """Reads all .md files in the procedural memory directory and returns a unified catalog of skills."""
    context_blocks = []
    
    # 1. Global procedural context
    if os.path.exists(PROCEDIMENTAL_DIR):
        for filename in sorted(os.listdir(PROCEDIMENTAL_DIR)):
            if filename.endswith(".md"):
                content = read_procedural_memory(filename)
                if content:
                    context_blocks.append(f"--- Documentación Herramienta Global: {filename} ---\n{content}\n")
                    
    # 2. Agent-specific procedural context
    if agent_name:
        agent_procedimental_dir = os.path.join(AGENT_CORE_DIR, "sub_agents", agent_name, "procedimental")
        if os.path.exists(agent_procedimental_dir):
            for filename in sorted(os.listdir(agent_procedimental_dir)):
                if filename.endswith(".md"):
                    with open(os.path.join(agent_procedimental_dir, filename), 'r', encoding='utf-8') as f:
                        context_blocks.append(f"--- Documentación Herramienta Específica del Agente ({agent_name}): {filename} ---\n{f.read()}\n")
                        
    result = "\n".join(context_blocks)
    if len(result) > MAX_MEMORY_TOTAL_CHARS:
        result = result[:MAX_MEMORY_TOTAL_CHARS] + "\n[... documentación truncada por límite de tokens]"
    return result

@tool
def administrar_memoria_episodica(accion: str, archivo: str, contenido: str = "", agente: str = None) -> str:
    """
    Gestiona la Memoria Episódica (preferencias, recuerdos, identidades).
    Si se especifica 'agente', se guardará en su carpeta privada (ej. sub_agents/finance/episodica/).
    Si NO se especifica 'agente', se guardará en la memoria global compartida.
    
    Args:
        accion: 'leer', 'actualizar' o 'agregar'.
        archivo: Nombre del archivo (ej: 'preferencias.md').
        contenido: El texto que deseas guardar o añadir.
        agente: (Opcional) El nombre del sub-agente para memoria privada.
    """
    if not archivo.endswith('.md'):
        archivo += '.md'
    
    if agente:
        base_dir = os.path.join(AGENT_CORE_DIR, "sub_agents", agente, "episodica")
    else:
        base_dir = EPISODICA_DIR
        
    file_path = os.path.join(base_dir, archivo)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    if accion == 'leer':
        if not os.path.exists(file_path):
            return f"❌ El archivo '{archivo}' no existe en memoria del agente '{agente or 'global'}'."
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    elif accion == 'actualizar':
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(contenido or "")
        return f"✅ Archivo '{archivo}' de '{agente or 'memoria global'}' sobrescrito."
        
    elif accion == 'agregar':
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{contenido}")
        return f"✅ Contenido añadido a '{archivo}' en '{agente or 'memoria global'}'."
    
    return f"❌ Acción '{accion}' no válida."

@tool
def administrar_memoria_procedimental(accion: str, archivo: str, contenido: str = "", agente: str = None) -> str:
    """
    Gestiona la Memoria Procedimental (cómo comportarse, reglas de negocio, habilidades).
    Úsalo para dar instrucciones persistentes a un agente específico sobre su rol o formato.
    
    Args:
        accion: 'leer', 'actualizar' o 'agregar'.
        archivo: Nombre del archivo (ej: 'instrucciones_rol.md').
        contenido: Las instrucciones o reglas a guardar.
        agente: (Opcional) El nombre del sub-agente para reglas privadas.
    """
    if not archivo.endswith('.md'):
        archivo += '.md'
        
    if agente:
        base_dir = os.path.join(AGENT_CORE_DIR, "sub_agents", agente, "procedimental")
    else:
        base_dir = PROCEDIMENTAL_DIR
        
    file_path = os.path.join(base_dir, archivo)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    if accion == 'leer':
        if not os.path.exists(file_path):
            return f"❌ No hay instrucciones procedimentales en '{archivo}' para '{agente or 'global'}'."
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    elif accion == 'actualizar':
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(contenido or "")
        return f"✅ Reglas procedimentales de '{archivo}' para '{agente or 'global'}' actualizadas."
        
    elif accion == 'agregar':
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{contenido}")
        return f"✅ Nuevas reglas añadidas a '{archivo}' para '{agente or 'global'}'."
    
    return f"❌ Acción '{accion}' no válida."

if __name__ == "__main__":
    init_memory_structure()
