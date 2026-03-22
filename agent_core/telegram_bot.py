import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update, Bot
from dotenv import load_dotenv

# Base .env loader just in case
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Permite ejecutar este archivo desde cualquier ruta
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import SelfExtendingAgent
from scheduler_manager import start_scheduler, stop_scheduler
from utils.audio_utils import transcribir_audio
from api_endpoints import router as api_router
from setup_manager import setup_router, check_and_init_setup
from fastapi.middleware.cors import CORSMiddleware

# Verificar primero si el sistema requiere Setup y crear la llave de activación si aplica
check_and_init_setup()

agent = SelfExtendingAgent()

# ----- CONFIGURACIÓN DESPUÉS DE INICIALIZAR EL AGENTE (Y EL .ENV) -----
from dotenv import dotenv_values

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
env_config = dotenv_values(env_path)

TOKEN = env_config.get("TELEGRAM_TOKEN", "").strip()
if not TOKEN:
    print("\n[!] AVISO: No se configuró un TELEGRAM_TOKEN en el archivo .env.")
    print("[!] El bot de Telegram no arrancará, pero el servidor GUI continuará en pie para que puedas configurarlo.\n")
    bot = None
else:
    bot = Bot(token=TOKEN)

WEBHOOK_URL = env_config.get("WEBHOOK_URL", "").strip()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup: Inicializar agente y configurar webhook
    print("=> Inicializando Cerebro del Agente y Conexiones MCP...")
    try:
        await agent.initialize()
        app.state.agent_ready = True
    except Exception as e:
        print(f"\n⚠️  AVISO: El agente no pudo inicializarse: {e}")
        print("⚠️  El servidor GUI seguirá activo para que puedas completar el Setup.\n")
        app.state.agent_ready = False
    
    if bot and app.state.agent_ready:
        if WEBHOOK_URL:
            webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/webhook"
            print(f"=> Configurando Webhook en Telegram: {webhook_endpoint}")
            await bot.set_webhook(url=webhook_endpoint)
        else:
            print("\\n=======================================================")
            print("=> ADVERTENCIA: WEBHOOK_URL no está configurado.")
            print("=> Telegram no sabrá adónde enviar los mensajes.")
            print("=> Abre tu archivo agent_core/.env y añade la clave WEBHOOK_URL=https://tu-url")
            print("=======================================================\\n")
            
        # Start the async job scheduler and pass the bot instance and agent instance for messaging and tasks
        start_scheduler(bot_instance=bot, agent_instance=agent)
    else:
        print("=> Telegram desactivado. Usa el GUI Onboarding para configurarlo.")
        start_scheduler(bot_instance=None, agent_instance=agent)
        
    yield
    
    # Cleanup
    print("=> Limpiando conexiones...")
    stop_scheduler()
    await agent.cleanup()
    if bot:
        try:
            await bot.delete_webhook()
        except Exception:
            pass

async def reload_telegram_bot():
    """Recarga el bot, el webhook y el scheduler post-setup sin reiniciar Docker."""
    global bot
    import os
    from dotenv import dotenv_values
    from aiogram import Bot
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    new_config = dotenv_values(env_path)
    
    tk = new_config.get("TELEGRAM_TOKEN", "").strip()
    wh = new_config.get("WEBHOOK_URL", "").strip()
    
    try:
        # Si ya había un bot vivo, limpiamos el webhook viejo si es posible
        if bot:
            try:
                await bot.delete_webhook()
            except:
                pass
                
        if tk:
            bot = Bot(token=tk)
            if wh:
                webhook_endpoint = f"{wh.rstrip('/')}/webhook"
                print(f"\\n=> 🔄 Setup Terminado: Configurando Webhook en Telegram: {webhook_endpoint}")
                await bot.set_webhook(url=webhook_endpoint)
            else:
                print("\\n=> 🔄 Setup Terminado: Telegram activado pero sin Webhook.")
            
            # Actualizamos también el scheduler para que el bot pueda enviar recordatorios
            from agent_core.scheduler_manager import update_scheduler_bot
            update_scheduler_bot(bot)
            
        else:
            bot = None
    except Exception as e:
        print(f"\\n⚠️  No se pudo recargar el bot de Telegram al Vuelo: {e}")

app = FastAPI(lifespan=lifespan)
app.state.agent = agent

# Habilitar CORS para desarrollo local (Angular)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar API para la GUI
app.include_router(setup_router)
app.include_router(api_router)

import re

def format_telegram_html(text: str) -> str:
    """Convierte Markdown básico del LLM a HTML compatible con Telegram para evitar crash de parseo."""
    # 1. Escapar <, >, y & pero no afectar lo que agreguemos después
    # (Telegram es muy estricto con las etiquetas no cerradas o caracteres como <)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 2. Negritas: **texto** -> <b>texto</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # 3. Cursiva: *texto* o _texto_ -> <i>texto</i> (Cuidando de no agarrar listas de markdown como * item)
    text = re.sub(r'(?<!\*)\*(?!\s)(?!\*)(.*?)(?<!\s)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'\b_(.*?)_\b', r'<i>\1</i>', text)
    
    # 4. Código Inline: `texto` -> <code>texto</code>
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    # 5. Enlaces: [texto](url) -> <a href="url">texto</a>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    
    # Listas: dejar los asteriscos iniciales de listas como texto plano
    
    return text

async def handle_message_background(chat_id: int, text: str):
    """Procesar el mensaje con el Agente en segundo plano para no bloquear el ACK del webhook."""
    try:
        # Check monthly quota first
        from utils.token_tracker import check_budget_exceeded
        is_exceeded, alert_msg = check_budget_exceeded()
        if is_exceeded:
            try:
                from telegram.constants import ParseMode
                # telegram markdown doesn't like some characters unescaped, but since we only use basic bold, we format basic
                alert_html = alert_msg.replace('*', '<b>').replace(' \n', '\n').replace('\n\n', '<br><br>')
                # Let's just use text to avoid parsing errors
                await bot.send_message(chat_id=chat_id, text=alert_msg)
            except Exception:
                await bot.send_message(chat_id=chat_id, text=alert_msg)
            return

        # Enviar estado "Escribiendo..." para dar feedback visual
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Procesar con la IA reteniendo el hilo de conversación usando el chat_id
        thread_id = str(chat_id)
        respuesta = await agent.process_message(text, thread_id=thread_id)
        
        # Parsear la respuesta y enviar usando HTML mode
        html_response = format_telegram_html(respuesta)
        
        try:
            from telegram.constants import ParseMode
            await bot.send_message(chat_id=chat_id, text=html_response, parse_mode=ParseMode.HTML)
        except Exception as parse_e:
            print(f"Error parseando HTML para Telegram: {parse_e}. Enviando como texto plano.")
            await bot.send_message(chat_id=chat_id, text=respuesta)
            
    except Exception as e:
        print(f"Error en el procesamiento del agente: {e}")
        await bot.send_message(chat_id=chat_id, text=f"Ups, ocurrió un error interno: {e}")

@app.post("/webhook")
async def process_update(request: Request):
    """Endpoint que Telegram llamará cada vez que alguien interactúe con el bot."""
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        
        chat_id = None
        text_to_process = None
        
        if update.message:
            chat_id = update.message.chat_id
            
            # 1. Manejar mensajes de texto
            if update.message.text:
                text_to_process = update.message.text
                print(f"\n[Telegram] {update.message.from_user.first_name} (ID: {chat_id}): {text_to_process}")
            
            # 2. Manejar mensajes de voz o audio
            elif update.message.voice or update.message.audio:
                audio_obj = update.message.voice if update.message.voice else update.message.audio
                user_name = update.message.from_user.first_name
                print(f"\n[Telegram] Recibido audio de {user_name} (ID: {chat_id})")
                
                # Feedback inicial
                await bot.send_chat_action(chat_id=chat_id, action="record_voice")
                
                # Crear carpeta de descargas temporal
                download_dir = "/tmp/leygo_downloads"
                os.makedirs(download_dir, exist_ok=True)
                
                # Obtener el archivo de Telegram
                file_id = audio_obj.file_id
                telegram_file = await bot.get_file(file_id)
                
                # Generar ruta local
                ext = ".ogg" if update.message.voice else os.path.splitext(telegram_file.file_path)[1]
                file_name = f"{file_id}{ext}"
                local_path = os.path.join(download_dir, file_name)
                
                # Descargar
                await telegram_file.download_to_drive(local_path)
                
                # Transcribir usando Gemini
                transcription = await transcribir_audio(local_path)
                
                if transcription:
                    print(f"[Telegram] Audio transcrito: {transcription}")
                    # Enviar un mensajito de feedback de lo que entendió (opcional, pero ayuda a la experiencia)
                    # await bot.send_message(chat_id=chat_id, text=f"🎤 _Entendí: {transcription}_", parse_mode="Markdown")
                    text_to_process = transcription
                else:
                    await bot.send_message(chat_id=chat_id, text="Lo siento, no pude procesar el audio correctamente.")
                
                # Limpiar archivo temporal
                try: os.remove(local_path)
                except: pass
                
            if chat_id and text_to_process:
                # Lanzar tarea concurrente para responder antes de los 10 segundos de Timeout de Telegram
                asyncio.create_task(handle_message_background(chat_id, text_to_process))
                
    except Exception as e:
        print(f"Error procesando el payload del webhook: {e}")
        import traceback
        traceback.print_exc()
        
    # Devolver HTTP 200 OK rápido
    return {"ok": True}

@app.post("/google-chat-webhook")
async def google_chat_webhook(request: Request):
    """Endpoint para recibir mensajes de Google Chat y reenviarlos al admin de Telegram."""
    try:
        payload = await request.json()
        
        # Google Chat hace un ping inicial de tipo 'ADDED_TO_SPACE'
        event_type = payload.get("type")
        
        # Obtener el Chat ID de Telegram del admin (debe configurarlo en .env)
        admin_chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
        
        if event_type == "ADDED_TO_SPACE":
            space = payload.get("space", {}).get("displayName", "un espacio nuevo")
            print(f"\\n[Google Chat Webhook] El bot fue añadido a {space}")
            if admin_chat_id:
                asyncio.create_task(bot.send_message(chat_id=admin_chat_id, text=f"🤖 <b>Bot conectado a Google Chat:</b> {space}", parse_mode="HTML"))
            # Respuesta requerida por Google Chat
            return {"text": f"¡Gracias por agregarme a {space}! Estoy conectado a Telegram."}
            
        elif event_type == "MESSAGE":
            message = payload.get("message", {})
            sender = message.get("sender", {}).get("displayName", "Alguien")
            space = payload.get("space", {}).get("displayName", "Mensaje Directo")
            text = message.get("text", "[Sin texto]")
            
            notificacion = f"🔔 <b>Nuevo mensaje en Google Chat</b>\\n🗣 <b>De:</b> {sender} <i>({space})</i>\\n📝 {text}"
            
            if admin_chat_id:
                # Lanzamos una subrutina en background para no colgar la rta de Google Chat
                asyncio.create_task(bot.send_message(chat_id=admin_chat_id, text=notificacion, parse_mode="HTML"))
            else:
                print(f"\\n[Google Chat Webhook] Recibido mensaje pero TELEGRAM_ADMIN_CHAT_ID no está configurado:\\n{notificacion}")
                
        # Para Google Chat Webhooks siempre hay que devolver un dict vacío o mensaje simple 
        # para indicar recibo y evitar errores en el panel de Cloud.
        return {}
        
    except Exception as e:
        print(f"Error procesando el payload de Google Chat: {e}")
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor Webhook en puerto 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
