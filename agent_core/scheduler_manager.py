import os
import asyncio
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from telegram import Bot

# Global bot instance that will be set by the telegram app
TELEGRAM_BOT_INSTANCE: Bot = None

# Configuración de almacenamiento persistente
MEMORIA_RECORDATORIOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria", "episodica", "recordatorios.json")

# Global scheduler instance
scheduler = AsyncIOScheduler()

def _guardar_estado_jobs():
    """Serializa las tareas actuales del scheduler a un archivo JSON."""
    jobs_data = []
    
    for job in scheduler.get_jobs():
        job_info = {
            "id": job.id,
            "name": job.name,
            "args": list(job.args) if job.args else []
        }
        
        # Guardar atributos según el tipo de trigger
        if hasattr(job.trigger, 'interval'):
            job_info["type"] = "interval"
            job_info["interval_minutes"] = job.trigger.interval.total_seconds() / 60.0
        else:
            job_info["type"] = "date"
            if job.next_run_time:
                job_info["next_run_time_iso"] = job.next_run_time.isoformat()
            else:
                continue # Si ya pasó y no tiene next run, ignorar

        jobs_data.append(job_info)
        
    os.makedirs(os.path.dirname(MEMORIA_RECORDATORIOS_PATH), exist_ok=True)
    with open(MEMORIA_RECORDATORIOS_PATH, 'w', encoding='utf-8') as f:
        json.dump(jobs_data, f, ensure_ascii=False, indent=4)

def _cargar_estado_jobs():
    """Carga y reinyecta las tareas desde el JSON."""
    if not os.path.exists(MEMORIA_RECORDATORIOS_PATH):
        return
        
    try:
        with open(MEMORIA_RECORDATORIOS_PATH, 'r', encoding='utf-8') as f:
            jobs_data = json.load(f)
            
        now = datetime.now()
        for job_info in jobs_data:
            job_type = job_info.get("type")
            args = job_info.get("args", [])
            name = job_info.get("name")
            job_id = job_info.get("id")
            
            # Chequear si este ID ya existe para evitar duplicados al reiniciar múltiples veces
            if scheduler.get_job(job_id):
                continue
                
            if job_type == "interval":
                minutes = job_info.get("interval_minutes")
                if minutes and len(args) >= 2:
                    scheduler.add_job(
                        _send_dynamic_telegram_reminder,
                        'interval',
                        minutes=minutes,
                        args=args,
                        name=name,
                        id=job_id
                    )
            elif job_type == "date":
                iso_time = job_info.get("next_run_time_iso")
                if iso_time and len(args) >= 2:
                    run_date = datetime.fromisoformat(iso_time)
                    # Solo resucitar recordatorios en el futuro
                    if run_date.tzinfo is not None and now.tzinfo is None:
                        now_aware = now.astimezone()
                        es_futuro = run_date > now_aware
                    else:
                        es_futuro = run_date > now
                        
                    if es_futuro:
                        scheduler.add_job(
                            _send_telegram_reminder,
                            'date',
                            run_date=run_date,
                            args=args,
                            name=name,
                            id=job_id
                        )
        print(f"=> Se cargaron {len(scheduler.get_jobs())} tareas del almacenamiento episódico.")
    except Exception as e:
        print(f"Error cargando recordatorios: {e}")

async def _send_telegram_reminder(chat_id: str, mensaje: str):
    """Callback function executed by the scheduler."""
    global TELEGRAM_BOT_INSTANCE
    
    # Intento lazy de cargar el bot si no fue proveído por webhook
    if not TELEGRAM_BOT_INSTANCE:
        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            TELEGRAM_BOT_INSTANCE = Bot(token=token)

    if TELEGRAM_BOT_INSTANCE:
        # Si estamos en CLI y hay un ID global de telegram en .env, forzar su uso.
        if chat_id == "default_session":
            global_chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if global_chat_id:
                chat_id = global_chat_id
            else:
                 print(f"\\n⏰ [RECORDATORIO LOCAL PENEDIENTE]: {mensaje}\\n")
                 return
                 
        try:
            await TELEGRAM_BOT_INSTANCE.send_message(chat_id=chat_id, text=f"{mensaje}")
        except Exception as e:
            print(f"Error enviando recordatorio por Telegram: {e}")
    else:
        print(f"\\n⏰ [RECORDATORIO PENEDIENTE para {chat_id}]: {mensaje}\\n")
        
    # Limpiar JSON tras enviar un date
    # Le damos un margen pequeño para que la función termine internamente en apscheduler
    asyncio.create_task(asyncio.sleep(2))
    _guardar_estado_jobs()

async def _send_dynamic_telegram_reminder(chat_id: str, prompt_instruccion: str):
    """Callback function executed periodically by the scheduler that uses Gemini to generate the text."""
    global TELEGRAM_BOT_INSTANCE
    
    if not TELEGRAM_BOT_INSTANCE:
        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            TELEGRAM_BOT_INSTANCE = Bot(token=token)

    # Autogenerate text with Gemini
    try:
        mini_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)
        response = await mini_llm.ainvoke(
            [HumanMessage(content=f"Genera un mensaje corto directo y amigable cumpliendo esta instrucción: '{prompt_instruccion}'. No repitas lo mismo de siempre, sé creativo. IMPORTANTE: Devuelve ÚNICAMENTE el mensaje, sin saludos iniciales, sin afirmaciones previas como 'Claro, aquí tienes', ni texto conversacional extra.")]
        )
        mensaje_dinamico = response.content.strip()
    except Exception as e:
        mensaje_dinamico = f"⏰ [Recordatorio Recurrente] (Error generando contenido: {e})"

    if TELEGRAM_BOT_INSTANCE:
        if chat_id == "default_session":
            global_chat_id = os.getenv("TELEGRAM_CHAT_ID")
            if global_chat_id:
                chat_id = global_chat_id
            else:
                 print(f"\\n⏰ [RUTINA LOCAL PENDIENTE]: {mensaje_dinamico}\\n")
                 return
                 
        try:
            await TELEGRAM_BOT_INSTANCE.send_message(chat_id=chat_id, text=mensaje_dinamico)
        except Exception as e:
            print(f"Error enviando rutina por Telegram: {e}")
    else:
        print(f"\\n⏰ [RUTINA PENDIENTE para {chat_id}]: {mensaje_dinamico}\\n")

def start_scheduler(bot_instance: Bot = None):
    """Starts the global scheduler."""
    global TELEGRAM_BOT_INSTANCE
    if bot_instance:
        TELEGRAM_BOT_INSTANCE = bot_instance
        
    if not scheduler.running:
        scheduler.start()
        _cargar_estado_jobs()
        print("=> Sistema APScheduler de recordatorios iniciado.")

def stop_scheduler():
    """Stops the global scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("=> Sistema APScheduler detenido.")

@tool
def programar_recordatorio(mensaje: str, chat_id: str, minutos_desde_ahora: int = None, hora_exacta_iso: str = None) -> str:
    """
    Programa un recordatorio que se enviará asíncronamente al usuario por mensaje de texto.
    Se requiere definir o 'minutos_desde_ahora' (entero de minutos de retraso) 
    o 'hora_exacta_iso' (fecha y hora en formato ISO 8601, ej. '2026-03-10T23:30:00-03:00').
    El chat_id en telegram_bot es siempre el thread_id pasado en la metadata del prompt actual.
    
    Args:
        mensaje: El texto que deseas enviarle de vuelta al usuario como recordatorio.
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        minutos_desde_ahora: Cantidad de minutos a esperar para enviar el mensaje. 
        hora_exacta_iso: Fecha/hora exacta deseada si no se usa retraso relativo.
        
    Returns:
        Un string informando si la tarea fue exitosamente encolada.
    """
    if not chat_id:
        return "Error: chat_id no definido. No se puede programar sin saber a quién enviarlo."
        
    if not minutos_desde_ahora and not hora_exacta_iso:
         return "Error: Debes proveer al menos 'minutos_desde_ahora' o 'hora_exacta_iso'."

    run_date = None
    if minutos_desde_ahora is not None:
        run_date = datetime.now() + timedelta(minutes=int(minutos_desde_ahora))
    elif hora_exacta_iso:
        try:
            run_date = datetime.fromisoformat(hora_exacta_iso)
        except ValueError:
            return "Error: hora_exacta_iso tiene un formato inválido. Debe ser ISO 8601 válido con o sin huso horario."

    # Recordatorio del pasado?
    now = datetime.now()
    if run_date.tzinfo is not None and now.tzinfo is None:
        # Prevent timezone naive vs aware comparison error
        now = now.astimezone()
        
    if run_date < now:
         return f"Error: La fecha calculada {run_date} está en el pasado según la hora actual {now}."
         
    # Añadir trabajo asíncrono
    scheduler.add_job(
        _send_telegram_reminder,
        'date',
        run_date=run_date,
        args=[chat_id, mensaje],
        name=mensaje[:50] # Guardamos un fragmento del mensaje como ID visual
    )
    _guardar_estado_jobs()
    
    return f"¡Recordatorio programado exitosamente! El mensaje será enviado el {run_date.strftime('%Y-%m-%d %H:%M:%S')}."

@tool
def programar_intervalo_dinamico(prompt_instruccion: str, chat_id: str, intervalo_minutos: int) -> str:
    """
    Programa una tarea periódica recurrente. Cada vez que transcurra 'intervalo_minutos', 
    el sistema utilizará una IA para generar un mensaje completamente nuevo basado en 
    'prompt_instruccion' y se lo enviará al usuario.
    
    Args:
        prompt_instruccion: Instrucción para la IA (ej. "Genera una frase estoica de motivación").
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        intervalo_minutos: Cada cuántos minutos debe repetirse (entero).
        
    Returns:
        String de confirmación.
    """
    if not chat_id:
        return "Error: chat_id no provisto."
        
    if not intervalo_minutos or intervalo_minutos <= 0:
        return "Error: intervalo_minutos debe ser mayor que 0."
        
    scheduler.add_job(
        _send_dynamic_telegram_reminder,
        'interval',
        minutes=intervalo_minutos,
        args=[chat_id, prompt_instruccion],
        name=f"Rutina: {prompt_instruccion[:30]}"
    )
    _guardar_estado_jobs()
    
    return f"¡Rutina dinámica programada! Cada {intervalo_minutos} minutos generarás y enviarás mensajes cumpliendo: '{prompt_instruccion}'."

@tool
def listar_recordatorios(chat_id: str) -> str:
    """
    Lista todos los recordatorios futuros pendientes programados para el usuario actual.
    
    Args:
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        
    Returns:
        Un texto formateado con la lista de recordatorios pendientes o un mensaje indicando que no hay ninguno.
    """
    if not chat_id:
        return "Error: chat_id no provisto."
        
    jobs = scheduler.get_jobs()
    user_jobs = []
    
    for job in jobs:
        # Los args del callback son [chat_id, mensaje/prompt] para ambos tipos de trabajos
        if job.args and len(job.args) >= 2 and str(job.args[0]) == str(chat_id):
            user_jobs.append(job)
            
    if not user_jobs:
        return "No tienes ningún recordatorio ni rutina recurrente programada."
        
    resultado = "Tus tareas programadas pendientes:\n"
    for i, job in enumerate(sorted(user_jobs, key=lambda j: j.next_run_time if j.next_run_time else datetime.max.replace(tzinfo=j.next_run_time.tzinfo if j.next_run_time else None)), 1):
        info = job.args[1]
        
        # Determinar si es periódico (basado en el trigger name o type)
        if hasattr(job.trigger, 'interval'):
            tipo = f"Rutina cada {job.trigger.interval}"
            fecha_str = f"Siguiente: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'Pausado'}"
            resultado += f"{i}. 🔄 [{tipo}] Instrucción LLM: '{info}' ({fecha_str})\n"
        else:
            fecha_str = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'Desconocida'
            resultado += f"{i}. ⏰ [Una vez] Mensaje: '{info}' (Para las: {fecha_str})\n"
        
    return resultado

@tool
def eliminar_recordatorio(chat_id: str, texto_busqueda: str) -> str:
    """
    Busca y elimina uno o varios recordatorios o rutinas programadas que coincidan parcialmente 
    (case-insensitive) con el 'texto_busqueda'.
    
    Args:
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        texto_busqueda: Fragmento del mensaje o instrucción LLM programada a eliminar.
        
    Returns:
        Un mensaje confirmando cuántas tareas se borraron y sus nombres.
    """
    if not chat_id:
        return "Error: chat_id no provisto."
        
    jobs = scheduler.get_jobs()
    eliminados = []
    
    for job in jobs:
        if job.args and len(job.args) >= 2 and str(job.args[0]) == str(chat_id):
            info_job = str(job.args[1]).lower()
            if texto_busqueda.lower() in info_job:
                try:
                    scheduler.remove_job(job.id)
                    eliminados.append(job.args[1][:50])
                except Exception as e:
                    print(f"Error borrando job {job.id}: {e}")
                    
    if eliminados:
        _guardar_estado_jobs()
        lista_borrados = "\\n- ".join(eliminados)
        return f"Éxito. Se eliminaron {len(eliminados)} tareas:\\n- {lista_borrados}"
        
    return f"No encontré ninguna tarea programada que contenga el texto '{texto_busqueda}'."
