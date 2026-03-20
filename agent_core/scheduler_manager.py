import os
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from telegram import Bot

# Timezone del usuario (configurable vía .env), por defecto Chile
TIMEZONE_STR = os.getenv("TZ", "America/Santiago")
TIMEZONE = ZoneInfo(TIMEZONE_STR)

# Global bot instance that will be set by the telegram app
TELEGRAM_BOT_INSTANCE: Bot = None
GLOBAL_AGENT_INSTANCE = None

# Configuración de almacenamiento persistente
MEMORIA_RECORDATORIOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria", "episodica", "recordatorios.json")

# Global scheduler instance — configurado con timezone de Chile
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

def __re_sync_jobs_listener(event):
    if getattr(event, 'exception', None) is None:
        try:
            guardar_estado_jobs()
        except Exception:
            pass

scheduler.add_listener(__re_sync_jobs_listener, EVENT_JOB_EXECUTED)

def guardar_estado_jobs():
    """Serializa las tareas actuales del scheduler a un archivo JSON."""
    jobs_data = []
    
    for job in scheduler.get_jobs():
        job_info = {
            "id": job.id,
            "name": job.name,
            "func_name": job.func.__name__,
            "args": list(job.args) if job.args else []
        }
        
        # Guardar atributos según el tipo de trigger
        if job.next_run_time:
            job_info["next_run_time_iso"] = job.next_run_time.isoformat()
        else:
            if not hasattr(job.trigger, 'interval') and not hasattr(job.trigger, 'fields'):
                continue # Si ya pasó y no tiene next run, y no es intervalo/cron, ignorar
                
        if hasattr(job.trigger, 'interval'):
            job_info["type"] = "interval"
            job_info["interval_minutes"] = job.trigger.interval.total_seconds() / 60.0
        elif hasattr(job.trigger, 'fields'):
            job_info["type"] = "cron"
            for f in job.trigger.fields:
                if f.name == 'hour':
                    job_info["cron_hour"] = str(f)
                elif f.name == 'minute':
                    job_info["cron_minute"] = str(f)
        else:
            job_info["type"] = "date"

        jobs_data.append(job_info)
        
    os.makedirs(os.path.dirname(MEMORIA_RECORDATORIOS_PATH), exist_ok=True)
    with open(MEMORIA_RECORDATORIOS_PATH, 'w', encoding='utf-8') as f:
        json.dump(jobs_data, f, ensure_ascii=False, indent=4)

def cargar_estado_jobs():
    """Carga y reinyecta las tareas desde el JSON."""
    if not os.path.exists(MEMORIA_RECORDATORIOS_PATH):
        return
        
    try:
        with open(MEMORIA_RECORDATORIOS_PATH, 'r', encoding='utf-8') as f:
            jobs_data = json.load(f)
        now = datetime.now(TIMEZONE)
        for job_info in jobs_data:
            job_type = job_info.get("type")
            args = job_info.get("args", [])
            name = job_info.get("name")
            job_id = job_info.get("id")
            func_name = job_info.get("func_name")
            
            # Chequear si este ID ya existe para evitar duplicados al reiniciar múltiples veces
            if scheduler.get_job(job_id):
                continue
                
            # Determinar qué función real cargar basándonos en func_name almacenado
            if func_name == "execute_agent_task":
                target_func = execute_agent_task
            elif func_name == "send_dynamic_telegram_reminder":
                target_func = send_dynamic_telegram_reminder
            else:
                target_func = send_telegram_reminder
                
            if job_type == "interval":
                minutes = job_info.get("interval_minutes")
                if minutes and len(args) >= 2:
                    scheduler.add_job(
                        target_func,
                        'interval',
                        minutes=minutes,
                        args=args,
                        name=name,
                        id=job_id
                    )
            elif job_type == "cron":
                hour = job_info.get("cron_hour", "*")
                minute = job_info.get("cron_minute", "*")
                
                # Helper to safely parse strings to int if possible
                def parse_cron_val(v):
                    if str(v).isdigit(): return int(v)
                    return v
                    
                if len(args) >= 2:
                    scheduler.add_job(
                        target_func,
                        'cron',
                        hour=parse_cron_val(hour),
                        minute=parse_cron_val(minute),
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
                            target_func,
                            'date',
                            run_date=run_date,
                            args=args,
                            name=name,
                            id=job_id
                        )
        print(f"=> Se cargaron {len(scheduler.get_jobs())} tareas del almacenamiento episódico.")
    except Exception as e:
        print(f"Error cargando recordatorios: {e}")

def _resolve_chat_id(chat_id: str) -> str:
    """Resuelve el chat_id a un ID numérico de Telegram válido.
    Si es 'default_session' o no es numérico, busca TELEGRAM_CHAT_ID en .env."""
    if chat_id and chat_id.lstrip('-').isdigit():
        return chat_id  # Es un ID numérico válido
    
    # Fallback: usar el chat_id global de .env
    global_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if global_chat_id:
        print(f"[Scheduler] chat_id '{chat_id}' no es numérico. Usando TELEGRAM_CHAT_ID={global_chat_id}")
        return global_chat_id
    
    return None  # No se pudo resolver

async def send_telegram_reminder(chat_id: str, mensaje: str):
    """Callback function executed by the scheduler."""
    global TELEGRAM_BOT_INSTANCE
    
    # Intento lazy de cargar el bot si no fue proveído por webhook
    if not TELEGRAM_BOT_INSTANCE:
        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            TELEGRAM_BOT_INSTANCE = Bot(token=token)

    if TELEGRAM_BOT_INSTANCE:
        resolved_id = _resolve_chat_id(chat_id)
        if not resolved_id:
            print(f"\\n⏰ [RECORDATORIO LOCAL PENDIENTE]: {mensaje}\\n")
            return
                 
        try:
            await TELEGRAM_BOT_INSTANCE.send_message(chat_id=resolved_id, text=f"{mensaje}")
        except Exception as e:
            print(f"Error enviando recordatorio por Telegram: {e}")
    else:
        print(f"\\n⏰ [RECORDATORIO PENEDIENTE para {chat_id}]: {mensaje}\\n")
        
    # Limpiar JSON tras enviar un date
    # Le damos un margen pequeño para que la función termine internamente en apscheduler
    asyncio.create_task(asyncio.sleep(2))
    guardar_estado_jobs()

async def send_dynamic_telegram_reminder(chat_id: str, prompt_instruccion: str):
    """Callback function executed periodically by the scheduler that uses Gemini to generate the text."""
    global TELEGRAM_BOT_INSTANCE
    
    if not TELEGRAM_BOT_INSTANCE:
        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            TELEGRAM_BOT_INSTANCE = Bot(token=token)

    from utils.token_tracker import check_budget_exceeded
    is_exceeded, alert_msg = check_budget_exceeded()
    if is_exceeded:
        print(f"[Scheduler] Bloqueado envío de rutina dinámica por cuota excedida: {prompt_instruccion[:20]}")
        if TELEGRAM_BOT_INSTANCE:
            resolved_id = _resolve_chat_id(chat_id)
            if resolved_id:
                try:
                    await TELEGRAM_BOT_INSTANCE.send_message(chat_id=resolved_id, text=f"Rutina pausada: {alert_msg}")
                except:
                    pass
        return

    # Autogenerate text with Gemini
    try:
        model_name = os.getenv("MODEL_SUPERVISOR", "gemini-2.5-flash-lite")
        mini_llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.7)
        response = await mini_llm.ainvoke(
            [HumanMessage(content=f"Genera un mensaje corto directo y amigable cumpliendo esta instrucción: '{prompt_instruccion}'. No repitas lo mismo de siempre, sé creativo. IMPORTANTE: Devuelve ÚNICAMENTE el mensaje, sin saludos iniciales, sin afirmaciones previas como 'Claro, aquí tienes', ni texto conversacional extra.")]
        )
        
        try:
            from utils.token_tracker import log_token_usage
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                in_tokens = response.usage_metadata.get("input_tokens", 0)
                out_tokens = response.usage_metadata.get("output_tokens", 0)
                log_token_usage(f"Routine: {prompt_instruccion[:15]}...", model_name, in_tokens, out_tokens, thread_id=str(chat_id))
        except Exception as t_err:
            print(f"Error trackeando tokens del Scheduler: {t_err}")
            
        content_raw = response.content
        if isinstance(content_raw, list):
            # En modelos recientes de Langchain, content puede ser un array de bloques.
            content_str = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in content_raw])
        else:
            content_str = str(content_raw)
            
        mensaje_dinamico = content_str.strip()
    except Exception as e:
        mensaje_dinamico = f"⏰ [Recordatorio Recurrente] (Error generando contenido: {e})"

    if TELEGRAM_BOT_INSTANCE:
        resolved_id = _resolve_chat_id(chat_id)
        if not resolved_id:
            print(f"\\n⏰ [RUTINA LOCAL PENDIENTE]: {mensaje_dinamico}\\n")
            return
                 
        try:
            await TELEGRAM_BOT_INSTANCE.send_message(chat_id=resolved_id, text=mensaje_dinamico)
        except Exception as e:
            print(f"Error enviando rutina por Telegram: {e}")
    else:
        print(f"\\n⏰ [RUTINA PENDIENTE para {chat_id}]: {mensaje_dinamico}\\n")

async def execute_agent_task(chat_id: str, instruccion: str):
    """Ejecuta una acción programada delegando todo el trabajo al Agente Auto-Extensivo."""
    global TELEGRAM_BOT_INSTANCE, GLOBAL_AGENT_INSTANCE
    
    if not TELEGRAM_BOT_INSTANCE:
        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            TELEGRAM_BOT_INSTANCE = Bot(token=token)
            
    from utils.token_tracker import check_budget_exceeded
    is_exceeded, alert_msg = check_budget_exceeded()
    if is_exceeded:
        print(f"[Scheduler] Bloqueado ejecución de tarea programada por cuota excedida: {instruccion[:20]}")
        if TELEGRAM_BOT_INSTANCE:
            resolved_id = _resolve_chat_id(chat_id)
            if resolved_id:
                try:
                    await TELEGRAM_BOT_INSTANCE.send_message(chat_id=resolved_id, text=f"Tarea programada pausada: {alert_msg}")
                except:
                    pass
        return
            
    try:
        if GLOBAL_AGENT_INSTANCE:
            print(f"\\n[Scheduler] 🤖 Ejecutando TAREA AUTÓNOMA para hilo {chat_id}: {instruccion}")
            # Procesar el input en background usando el stack de memoria
            respuesta = await GLOBAL_AGENT_INSTANCE.process_message(instruccion, thread_id=chat_id)
            
            # Enviar el resultado del agente mediante el bot a Telegram o GUI
            resolved_id = _resolve_chat_id(chat_id)
            if TELEGRAM_BOT_INSTANCE and resolved_id:
                import sys
                try:
                    # Intento de formateo bonito local si existe
                    from telegram_bot import format_telegram_html
                    from telegram.constants import ParseMode
                    html_response = format_telegram_html(respuesta)
                    await TELEGRAM_BOT_INSTANCE.send_message(chat_id=resolved_id, text=html_response, parse_mode=ParseMode.HTML)
                except Exception as e:
                    await TELEGRAM_BOT_INSTANCE.send_message(chat_id=resolved_id, text=respuesta)
            else:
                print(f"\\n⏰ [TAREA AUTÓNOMA LOCAL COMPLETADA]: {respuesta}\\n")
        else:
            print("[Scheduler Error] No hay instancia global del agente; no se puede procesar la tarea autónoma.")
    except Exception as e:
        print(f"Error procesando la tarea autónoma '{instruccion[:20]}...': {e}")
        try:
             await TELEGRAM_BOT_INSTANCE.send_message(chat_id=chat_id, text=f"Falló la ejecución programada de: {instruccion[:30]}...")
        except: pass

    asyncio.create_task(asyncio.sleep(2))
    guardar_estado_jobs()

def start_scheduler(bot_instance: Bot = None, agent_instance = None):
    """Starts the global scheduler."""
    global TELEGRAM_BOT_INSTANCE, GLOBAL_AGENT_INSTANCE
    if bot_instance:
        TELEGRAM_BOT_INSTANCE = bot_instance
    if agent_instance:
        GLOBAL_AGENT_INSTANCE = agent_instance
        
    if not scheduler.running:
        scheduler.start()
        cargar_estado_jobs()
        print("=> Sistema APScheduler de recordatorios iniciado.")

def stop_scheduler():
    """Stops the global scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("=> Sistema APScheduler detenido.")

@tool
def crear_recordatorio_solo_texto_para_usuario(mensaje: str, chat_id: str, minutos_desde_ahora: int = None, hora_exacta_iso: str = None) -> str:
    """
    Programa un simple recordatorio que se enviará asíncronamente al usuario por mensaje de texto.
    
    ¡ADVERTENCIA CRÍTICA!: NUNCA uses esta herramienta si el usuario te pide que *tú* hagas algo 
    en el futuro (como enviar un email, apagar un servidor, leer algo).
    
    ESTA HERRAMIENTA ES SÓLO PARA AVISOS DE TEXTO PURO HACIA EL USUARIO (ej. 'Recuerda tomar agua', 
    'Acuérdate de la reunión'). Si el usuario dice "quiero que envíes un email", "quiero realizar una accion",
    usa la herramienta 'agendar_accion_autonoma_agente'.
    
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
        run_date = datetime.now(TIMEZONE) + timedelta(minutes=int(minutos_desde_ahora))
    elif hora_exacta_iso:
        try:
            run_date = datetime.fromisoformat(hora_exacta_iso)
        except ValueError:
            return "Error: hora_exacta_iso tiene un formato inválido. Debe ser ISO 8601 válido con o sin huso horario."

    now = datetime.now(TIMEZONE)
    
    # Comparar run_date con now, asegurándose que ambos manejen tzinfo de forma parecida
    if run_date.tzinfo is not None and now.tzinfo is None:
        now = now.astimezone(run_date.tzinfo)
    elif run_date.tzinfo is None and now.tzinfo is not None:
        run_date = run_date.replace(tzinfo=now.tzinfo)
        
    if run_date < now:
         return f"Error: La fecha calculada {run_date} está en el pasado según la hora actual {now}."
         
    # Añadir trabajo asíncrono
    scheduler.add_job(
        send_telegram_reminder,
        'date',
        run_date=run_date,
        args=[chat_id, mensaje],
        name=mensaje[:50] # Guardamos un fragmento del mensaje como ID visual
    )
    guardar_estado_jobs()
    
    return f"¡Recordatorio de TEXTO SIMPLE programado exitosamente! El mensaje será enviado el {run_date.strftime('%Y-%m-%d %H:%M:%S')}."

@tool
def agendar_accion_autonoma_agente(instruccion_accion: str, chat_id: str, minutos_desde_ahora: int = None, hora_exacta_iso: str = None) -> str:
    """
    IMPORTANTE: Usa esta herramienta SI Y SOLO SI el usuario te pide programar/agendar una ACCIÓN REAL y AUTÓNOMA en el futuro 
    (ej. enviar un correo a Juan a las 8AM, pedirte resumir un reporte en 2 horas, ejecutar una herramienta luego). 
    NO la uses para simples recordatorios de texto (para eso usa 'programar_recordatorio').
    
    Se requiere definir o 'minutos_desde_ahora' (entero) o 'hora_exacta_iso' (fecha y hora en formato ISO 8601).
    El chat_id en telegram_bot es siempre el thread_id pasado en la metadata del prompt actual.
    
    Args:
        instruccion_accion: El prompt exacto que tú mismo (como agente) deberás ejecutar internamente llegado el momento (ej. "Mandar email a jesus diciendo que salí").
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        minutos_desde_ahora: Cantidad de minutos a esperar antes de que el agente procese la tarea internamente.
        hora_exacta_iso: Fecha/hora exacta (ej. '2026-03-10T23:30:00-03:00') deseada si no se usa minutos.
        
    Returns:
        Un string confirmando que la ACCIÓN AUTÓNOMA fue encolada con éxito en el programador de tareas y quedará activa aunque el sistema reinicie.
    """
    if not chat_id:
        return "Error: chat_id no provisto."
        
    if not minutos_desde_ahora and not hora_exacta_iso:
         return "Error: Debes proveer al menos 'minutos_desde_ahora' o 'hora_exacta_iso'."

    run_date = None
    if minutos_desde_ahora is not None:
        run_date = datetime.now(TIMEZONE) + timedelta(minutes=int(minutos_desde_ahora))
    elif hora_exacta_iso:
        try:
            run_date = datetime.fromisoformat(hora_exacta_iso)
        except ValueError:
            return "Error: hora_exacta_iso tiene un formato inválido. Debe ser ISO 8601 válido."

    now = datetime.now(TIMEZONE)
    
    # Comparar run_date con now, asegurándose que ambos manejen tzinfo de forma parecida
    if run_date.tzinfo is not None and now.tzinfo is None:
        now = now.astimezone(run_date.tzinfo)
    elif run_date.tzinfo is None and now.tzinfo is not None:
        run_date = run_date.replace(tzinfo=now.tzinfo)
        
    if run_date < now:
         return f"Error: La fecha calculada {run_date} está en el pasado según la hora actual {now}."
         
    scheduler.add_job(
        execute_agent_task,
        'date',
        run_date=run_date,
        args=[chat_id, instruccion_accion],
        name=f"TAREA ACTIVA AGENTE: {instruccion_accion[:40]}"
    )
    guardar_estado_jobs()
    
    return f"¡Tarea Ejecutora programada excelentemente! Arrancaré de nuevo y ejecutaré la siguiente instrucción a las {run_date.strftime('%Y-%m-%d %H:%M:%S')}: '{instruccion_accion}'."

@tool
def crear_rutina_texto_periodica_para_usuario(prompt_instruccion: str, chat_id: str, intervalo_minutos: int = None, hora_del_dia: str = None) -> str:
    """
    Programa una tarea periódica recurrente que enviará mensajes generados por IA.
    
    ¡ADVERTENCIA CRÍTICA!: ESTA HERRAMIENTA ES SOLO PARA MENSAJES RECURRENTES (ej. "dime una frase motivacional cada hora").
    NO la uses si el usuario te pide *hacer acciones repetitivas* (como revisar el correo o hacer scraping cada hora). 
    Para rutinas de ejecución de labores por parte tuya usa 'agendar_rutina_autonoma_agente'.
    
    Puedes configurar una recurrencia basada en cada X minutos (intervalo_minutos)
    o a una hora exacta todos los días (hora_del_dia en formato "HH:MM", ej. "11:30", "09:00", "22:15").
    Debes proveer sólo uno de los dos.
    
    Args:
        prompt_instruccion: Instrucción para la IA (ej. "Genera una frase estoica de motivación").
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        intervalo_minutos: Cada cuántos minutos debe repetirse (entero).
        hora_del_dia: Hora diaria específica formato "HH:MM" (reloj 24h).
        
    Returns:
        String de confirmación.
    """
    if not chat_id:
        return "Error: chat_id no provisto."
        
    if not intervalo_minutos and not hora_del_dia:
        return "Error: Debes proveer al menos intervalo_minutos o hora_del_dia."
        
    if intervalo_minutos:
        scheduler.add_job(
            send_dynamic_telegram_reminder,
            'interval',
            minutes=intervalo_minutos,
            args=[chat_id, prompt_instruccion],
            name=f"RUTINA TEXTO: {prompt_instruccion[:30]}"
        )
        msg_conf = f"¡Rutina programada! Cada {intervalo_minutos} minutos."
    elif hora_del_dia:
        try:
            h, m = hora_del_dia.split(":")
            scheduler.add_job(
                send_dynamic_telegram_reminder,
                'cron',
                hour=int(h),
                minute=int(m),
                args=[chat_id, prompt_instruccion],
                name=f"RUTINA TEXTO: {prompt_instruccion[:30]}"
            )
            msg_conf = f"¡Rutina programada! Todos los días a las {hora_del_dia}."
        except ValueError:
            return "Error: hora_del_dia debe tener el formato HH:MM."
            
    guardar_estado_jobs()
    return msg_conf + f" Se generarán mensajes cumpliendo: '{prompt_instruccion}'."

@tool
def agendar_rutina_autonoma_agente(instruccion_accion: str, chat_id: str, intervalo_minutos: int = None, hora_del_dia: str = None) -> str:
    """
    IMPORTANTE: Usa esta herramienta SI Y SOLO SI el usuario te pide programar/agendar una ACCIÓN REAL y AUTÓNOMA que 
    deba ejecutarse de forma PERIÓDICA/RECURRENTE (ej. "revisa mi correo cada 60 minutos", "resume las noticias a las 09:00").
    
    NO la uses para simples mensajes recurrentes hacia el usuario. Para acciones que el AGENTE debe hacer, usa esta.
    El chat_id en telegram_bot es siempre el thread_id pasado en la metadata del prompt actual.
    
    Puedes configurar una recurrencia basada en cada X minutos (intervalo_minutos)
    o a una hora exacta todos los días (hora_del_dia en formato "HH:MM", ej. "11:30", "09:00", "22:15").
    Debes proveer sólo uno de los dos.
    
    Args:
        instruccion_accion: El prompt exacto que tú mismo (como agente) deberás ejecutar internamente cada cierto tiempo.
        chat_id: ID del usuario o hilo actual (proporcionado en tu SystemPrompt o contexto).
        intervalo_minutos: Cada cuántos minutos debe ejecutarse la acción de forma automática.
        hora_del_dia: Hora diaria específica formato "HH:MM" (reloj 24h).
        
    Returns:
        Un string confirmando que la ACCIÓN RECURRENTE fue encolada con éxito.
    """
    if not chat_id:
        return "Error: chat_id no provisto."
        
    if not intervalo_minutos and not hora_del_dia:
        return "Error: Debes proveer al menos intervalo_minutos o hora_del_dia."
        
    if intervalo_minutos:
        scheduler.add_job(
            execute_agent_task,
            'interval',
            minutes=intervalo_minutos,
            args=[chat_id, instruccion_accion],
            name=f"RUTINA AGENTE: {instruccion_accion[:30]}"
        )
        msg_conf = f"¡Rutina de Tarea Ejecutora programada excelentemente! Me encenderé automáticamente cada {intervalo_minutos} minutos"
    elif hora_del_dia:
        try:
            h, m = hora_del_dia.split(":")
            scheduler.add_job(
                execute_agent_task,
                'cron',
                hour=int(h),
                minute=int(m),
                args=[chat_id, instruccion_accion],
                name=f"RUTINA AGENTE: {instruccion_accion[:30]}"
            )
            msg_conf = f"¡Rutina de Tarea Ejecutora programada excelentemente! Me encenderé todos los días a las {hora_del_dia}"
        except ValueError:
            return "Error: hora_del_dia debe tener el formato HH:MM."

    guardar_estado_jobs()
    return msg_conf + f" para ejecutar la siguiente instrucción: '{instruccion_accion}'."

@tool
def listar_tareas_programadas(chat_id: str) -> str:
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
    
    current_chat_id_resolved = _resolve_chat_id(chat_id)
    
    for job in jobs:
        # Los args del callback son [chat_id, mensaje/prompt] para ambos tipos de trabajos
        if job.args and len(job.args) >= 2:
            stored_chat_id_resolved = _resolve_chat_id(str(job.args[0]))
            if stored_chat_id_resolved == current_chat_id_resolved:
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
def eliminar_tarea_programada(chat_id: str, texto_busqueda: str) -> str:
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
    eliminados = [] # Keep this for the final message
    removed_count = 0
    search_term = texto_busqueda.lower()
    
    current_chat_id_resolved = _resolve_chat_id(chat_id)
    
    for job in jobs:
        if job.args and len(job.args) >= 2:
            stored_chat_id_resolved = _resolve_chat_id(str(job.args[0]))
            if stored_chat_id_resolved == current_chat_id_resolved:
                info = str(job.args[1]).lower()
                if search_term in info or search_term in job.name.lower():
                    try:
                        scheduler.remove_job(job.id)
                        removed_count += 1
                        eliminados.append(job.args[1][:50]) # Append to eliminados for the message
                    except Exception as e:
                        print(f"Error borrando job {job.id}: {e}")
                    
    if eliminados: # Check eliminados, not removed_count, for the message content
        guardar_estado_jobs()
        lista_borrados = "\\n- ".join(eliminados)
        return f"Éxito. Se eliminaron {len(eliminados)} tareas:\\n- {lista_borrados}"
        
    return f"No encontré ninguna tarea programada que contenga el texto '{texto_busqueda}'."
