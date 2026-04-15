import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.message import EmailMessage
import base64
from langchain_core.tools import tool
from google_auth import get_google_credentials

# ==========================================================
# 📧 GMAIL TOOLS
# ==========================================================

@tool
def leer_correos_recientes(max_resultados: int = 5, solo_no_leidos: bool = False, busqueda: str = "") -> str:
    """
    Lee los correos más recientes en la bandeja de entrada del usuario usando Gmail API.
    
    Args:
        max_resultados: El número máximo de correos a recuperar (por defecto 25).
        solo_no_leidos: Si es True, filtra y devuelve exclusivamente los correos que NO han sido leídos.
        busqueda: (Opcional) Texto o filtro tipo Gmail (ej. 'from:netflix' o 'proyecto') para una búsqueda específica.
    Returns:
        Un resumen en texto de los correos encontrados con remitente, asunto y snippet.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google. Dile al usuario que revise sus credenciales."

    try:
        service = build('gmail', 'v1', credentials=creds)
        
        list_options = {
            'userId': 'me',
            'maxResults': max_resultados
        }
        
        if not busqueda:
            etiquetas_busqueda = ['INBOX']
            if solo_no_leidos:
                etiquetas_busqueda.append('UNREAD')
            list_options['labelIds'] = etiquetas_busqueda
        else:
            query_parts = [busqueda]
            if solo_no_leidos: query_parts.append('is:unread')
            list_options['q'] = " ".join(query_parts)
            
        results = service.users().messages().list(**list_options).execute()
        messages = results.get('messages', [])

        if not messages:
            return "No se encontraron correos nuevos en la bandeja de entrada."

        resumen_correos = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['From', 'Subject', 'Message-ID']).execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            
            subject = "Sin asunto"
            sender = "Desconocido"
            message_id_header = ""
            for header in headers:
                if header['name'] == 'Subject':
                    subject = header['value']
                elif header['name'] == 'From':
                    sender = header['value']
                elif header['name'] == 'Message-ID':
                    message_id_header = header['value']
                    
            snippet = msg_data.get('snippet', '')
            label_ids = msg_data.get('labelIds', [])
            is_unread = 'UNREAD' in label_ids
            estado = "🔴 NO LEÍDO" if is_unread else "🟢 LEÍDO"
            
            thread_id = msg_data.get('threadId', '')
            
            # Extraemos las etiquetas personalizadas (ignorando las de sistema en mayúsculas como INBOX, UNREAD, CATEGORY_*)
            custom_labels = [lbl for lbl in label_ids if not lbl.isupper()]
            etiquetas_str = f" Etiquetas: {', '.join(custom_labels)}" if custom_labels else ""
            
            resumen_correos.append(f"- [ID: {msg['id']} | Thread: {thread_id} | Msg-ID: {message_id_header}] {estado}\\n  De: {sender}\\n  Asunto: {subject}{etiquetas_str}\\n  Resumen: {snippet}...\\n")

        return "Correos recientes:\\n" + "\\n".join(resumen_correos)
        
    except HttpError as error:
        return f"Ocurrió un error al leer Gmail: {error}"

@tool
def leer_hilo_correo(thread_id: str) -> str:
    """
    Lee un hilo completo de correos de Gmail para mantener el contexto histórico antes de responder o resumir.
    
    Args:
        thread_id: El ID del hilo a leer (se obtiene como 'Thread' en la salida de leer_correos_recientes).
    Returns:
        El contenido histórico de los mensajes dentro de ese hilo.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('gmail', 'v1', credentials=creds)
        thread = service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread.get('messages', [])
        
        historial = [f"--- HILO DE CORREOS ({len(messages)} mensajes) ---"]
        for msg in messages:
            headers = msg.get('payload', {}).get('headers', [])
            sender = next((h['value'] for h in headers if h['name'] == 'From'), "Desconocido")
            date_sent = next((h['value'] for h in headers if h['name'] == 'Date'), "Desconocido")
            snippet = msg.get('snippet', '')
            
            body_text = snippet
            try:
                parts = msg.get('payload', {}).get('parts', [])
                for part in parts:
                    if part.get('mimeType') == 'text/plain':
                        data = part.get('body', {}).get('data', '')
                        if data:
                            import base64
                            body_text = base64.urlsafe_b64decode(data).decode('utf-8')
                            body_text = body_text.replace('\r\n', '\n').strip()[:1000] # Limitar a 1k chars por msg
                            break
            except Exception:
                pass
                
            historial.append(f"\n> MENSAJE DE: {sender} (Fecha: {date_sent})\n{body_text}\n" + ("-"*40))
            
        return "\n".join(historial)
    except HttpError as error:
        return f"Ocurrió un error al leer el hilo de correos: {error}"

@tool
def enviar_correo(destinatario: str, asunto: str, cuerpo: str, responde_a_message_id: str = None, thread_id: str = None) -> str:
    """
    Envía un correo electrónico usando la cuenta de Gmail del usuario.
    
    Args:
        destinatario: El correo electrónico de la persona a quien enviar el mensaje (ej: 'juan@ejemplo.com').
        asunto: El asunto del correo.
        cuerpo: El mensaje o contenido del correo.
        responde_a_message_id: (Opcional) El encabezado 'Msg-ID' del correo original, sirve para responder sobre el mismo hilo.
        thread_id: (Opcional) El 'Thread' ID del correo original, de la mano con responde_a_message_id.
    Returns:
        Mensaje de confirmación del envío.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('gmail', 'v1', credentials=creds)
        
        # LLMs a veces envían saltos de línea literales '\\n', hay que convertirlos a reales
        cuerpo = cuerpo.replace('\\\\n', '\\n')
        
        message = EmailMessage()
        message.set_content(cuerpo)
        message['To'] = destinatario
        message['From'] = 'me'
        message['Subject'] = asunto
        
        if responde_a_message_id:
            message['In-Reply-To'] = responde_a_message_id
            message['References'] = responde_a_message_id

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        if thread_id:
            create_message['threadId'] = thread_id

        send_message = service.users().messages().send(userId="me", body=create_message).execute()
        return f"Correo enviado exitosamente con Message Id: {send_message['id']} / Thread: {send_message.get('threadId', 'N/A')}"
        
    except HttpError as error:
        return f"Ocurrió un error al intentar enviar el correo: {error}"


@tool
def modificar_etiquetas_correo(mensaje_id: str, etiquetas_a_agregar: list[str] = None, etiquetas_a_remover: list[str] = None, marcar_leido: bool = None) -> str:
    """
    Modifica las etiquetas de un correo electrónico específico. Si una etiqueta nueva no existe, la crea.
    
    Args:
        mensaje_id: El ID del mensaje de Gmail.
        etiquetas_a_agregar: (Opcional) Lista de nombres de etiquetas a agregar (ej: ['Trabajo', 'Urgente']).
        etiquetas_a_remover: (Opcional) Lista de nombres de etiquetas a remover.
        marcar_leido: (Opcional) Si es True, marca el correo como leído. Si es False, lo marca como no leído.
    Returns:
        Mensaje de éxito con las modificaciones realizadas.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('gmail', 'v1', credentials=creds)
        
        # 1. Obtener todas las etiquetas existentes de la cuenta para mapear Nombre -> ID
        labels_result = service.users().labels().list(userId='me').execute()
        existing_labels = labels_result.get('labels', [])
        label_name_to_id = {lbl['name'].lower(): lbl['id'] for lbl in existing_labels}
        
        add_label_ids = []
        remove_label_ids = []
        
        # Procesar estado Leído / No leído a través de la etiqueta de sistema 'UNREAD'
        if marcar_leido is True:
            remove_label_ids.append('UNREAD')
        elif marcar_leido is False:
            add_label_ids.append('UNREAD')

        # Procesar etiquetas a agregar
        if etiquetas_a_agregar:
            for name in etiquetas_a_agregar:
                name_lower = name.lower()
                if name_lower in label_name_to_id:
                    add_label_ids.append(label_name_to_id[name_lower])
                else:
                    # Crear la etiqueta si no existe
                    try:
                        new_label = service.users().labels().create(
                            userId='me', 
                            body={'name': name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
                        ).execute()
                        add_label_ids.append(new_label['id'])
                        label_name_to_id[name_lower] = new_label['id']
                    except Exception as e:
                        return f"Error al intentar crear la nueva etiqueta '{name}': {e}"
                        
        # Procesar etiquetas a remover
        if etiquetas_a_remover:
            for name in etiquetas_a_remover:
                name_lower = name.lower()
                if name_lower in label_name_to_id:
                    remove_label_ids.append(label_name_to_id[name_lower])

        # 2. Ejecutar la modificación
        body = {}
        if add_label_ids:
            body['addLabelIds'] = add_label_ids
        if remove_label_ids:
            body['removeLabelIds'] = remove_label_ids
            
        if not body:
            return "No se solicitaron modificaciones válidas para el correo."

        service.users().messages().modify(userId='me', id=mensaje_id, body=body).execute()
        
        acciones = []
        if add_label_ids: acciones.append(f"Agregadas/Marcas: {add_label_ids}")
        if remove_label_ids: acciones.append(f"Removidas/Desmarcas: {remove_label_ids}")
        
        return f"Correo modificado con éxito. Acciones: {', '.join(acciones)}"

    except HttpError as error:
        return f"Ocurrió un error al modificar el correo: {error}"


# ==========================================================
# 📅 GOOGLE CALENDAR TOOLS
# ==========================================================

@tool
def listar_eventos_calendario(dias_a_futuro: int = 7, fecha_inicio_iso: str = None, fecha_fin_iso: str = None) -> str:
    """
    Obtiene los eventos del Google Calendar principal del usuario. Permite buscar en el futuro o en fechas específicas/pasadas.
    
    Args:
        dias_a_futuro: Cuántos días buscar si no se dan fechas exactas (por defecto 7).
        fecha_inicio_iso: (Opcional) Fecha de inicio estricta en ISO (ej. '2026-05-10T00:00:00Z').
        fecha_fin_iso: (Opcional) Fecha final estricta. Si pasas inicio pero no fin, asume 1 día tras el inicio.
    Returns:
        Una lista de eventos en texto legible.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('calendar', 'v3', credentials=creds)

        # Helper: garantizar formato RFC3339 estricto
        def normalizar_iso(fecha_str: str) -> str:
            if not fecha_str: return None
            # Quitar Z para normalizar
            fecha_str = fecha_str.replace('Z', '')
            # Si es solo fecha (ej: 2026-04-29), agregar hora 00:00:00
            if 'T' not in fecha_str:
                fecha_str += 'T00:00:00'
            # Asegurar timezone offset or Z
            if '+' not in fecha_str and '-' not in fecha_str.split('T')[1]:
                fecha_str += 'Z'
            return fecha_str
            
        # Configurar límites de tiempo
        now = datetime.datetime.utcnow()
        if fecha_inicio_iso:
            timeMin = normalizar_iso(fecha_inicio_iso)
            if fecha_fin_iso:
                timeMax = normalizar_iso(fecha_fin_iso)
            else:
                try:
                    dt_str = timeMin.replace('Z', '+00:00')
                    dt = datetime.datetime.fromisoformat(dt_str)
                    dt_end = dt + datetime.timedelta(days=1)
                    timeMax = dt_end.strftime('%Y-%m-%dT%H:%M:%SZ')
                except Exception as e:
                    timeMax = (now + datetime.timedelta(days=dias_a_futuro)).strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            timeMin = now.strftime('%Y-%m-%dT%H:%M:%SZ')
            timeMax = (now + datetime.timedelta(days=dias_a_futuro)).strftime('%Y-%m-%dT%H:%M:%SZ')

        events_result = service.events().list(
            calendarId='primary', timeMin=timeMin, timeMax=timeMax,
            maxResults=20, singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            return f"No hay eventos programados en los próximos {dias_a_futuro} días."

        lista_eventos = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            event_id = event.get('id', 'N/A')
            status = event.get('status', 'N/A') # confirmado, tentativo, cancelado
            
            user_response = "N/A"
            otros_invitados = []
            
            for attendee in event.get('attendees', []):
                email_invitado = attendee.get('email', 'N/A')
                status_invitado = attendee.get('responseStatus', 'N/A')
                
                if attendee.get('self'):
                    user_response = status_invitado
                else:
                    otros_invitados.append(f"{email_invitado} ({status_invitado})")
                    
            invitados_str = f" | Invitados: {', '.join(otros_invitados)}" if otros_invitados else " | Sin más invitados"
            
            # Buscar links e ubicaciones
            meet_link = event.get('hangoutLink')
            location = event.get('location')
            
            conexion_str = ""
            if meet_link:
                conexion_str += f" | 💻 Reunion Virtual: {meet_link}"
            if location:
                conexion_str += f" | 📍 Ubicación: {location}"
            if not meet_link and not location:
                conexion_str += f" | Sin ubicación/link"
            
            lista_eventos.append(f"- [{start}] {event.get('summary', 'Sin título')} (ID: {event_id}) [Tu respuesta: {user_response}]{invitados_str}{conexion_str}")

        return f"Próximos eventos (Próximos {dias_a_futuro} días):\\n" + "\\n".join(lista_eventos)

    except HttpError as error:
        return f"Ocurrió un error al leer el Calendario: {error}"

@tool
def responder_evento_calendario(evento_id: str, respuesta: str) -> str:
    """
    Permite aceptar, rechazar o marcar como tentativo una invitación de calendario.
    
    Args:
        evento_id: El ID del evento a responder.
        respuesta: Tu respuesta a la invitación. Puede ser 'accepted' (aceptar), 'declined' (rechazar), o 'tentative' (tentativo).
    Returns:
        Un string indicando si la operación fue exitosa.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    valid_responses = ['accepted', 'declined', 'tentative']
    if respuesta not in valid_responses:
        return f"Error: '{respuesta}' no es una respuesta válida. Opciones: {valid_responses}"

    try:
        service = build('calendar', 'v3', credentials=creds)
        
        # 1. Obtener el evento actual
        event = service.events().get(calendarId='primary', eventId=evento_id).execute()
        
        # 2. Modificar el attendee que corresponde al usuario actual (self = True)
        attendees = event.get('attendees', [])
        found_self = False
        
        for attendee in attendees:
            if attendee.get('self'):
                attendee['responseStatus'] = respuesta
                found_self = True
                break
                
        if not found_self:
            # Si no estábamos formalmente en la lista, podemos intentar agregarnos si el evento lo permite
            # O simplemente devolver error
            return f"Hubo un problema: No figuras como invitado ('attendee') en el evento {evento_id}."
            
        # 3. Actualizar el evento
        # sendUpdates='all' notifica a los demás del cambio
        updated_event = service.events().update(
            calendarId='primary',
            eventId=evento_id,
            body=event,
            sendUpdates='all'
        ).execute()

        status_traducido = "Aceptado" if respuesta == "accepted" else ("Rechazado" if respuesta == "declined" else "Tentativo")
        return f"Éxito: Has marcado tu respuesta al evento '{updated_event.get('summary', 'Sin Título')}' como {status_traducido}."

    except HttpError as error:
        return f"Ocurrió un error al responder la invitación: {error}"

@tool
def comprobar_disponibilidad_calendario(fecha_inicio_iso: str, fecha_fin_iso: str) -> str:
    """
    Analiza la agenda del usuario buscando conflictos, reuniones o huecos libres 
    (Free/Busy) en un rango de fechas. Muy útil antes de agendar un evento nuevo.
    
    Args:
        fecha_inicio_iso: Fecha/hora de inicio en ISO (ej: '2026-03-12T09:00:00Z').
        fecha_fin_iso: Fecha/hora de fin en ISO (ej: '2026-03-12T18:00:00Z').
    Returns:
        Un informe textual detallando si el espacio está libre u ocupado.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('calendar', 'v3', credentials=creds)
        
        def normalizar_iso(fecha_str: str) -> str:
            if not fecha_str: return None
            fecha_str = fecha_str.replace('Z', '')
            if 'T' not in fecha_str: fecha_str += 'T00:00:00'
            if '+' not in fecha_str and '-' not in fecha_str.split('T')[1]: fecha_str += 'Z'
            return fecha_str
            
        body = {
            "timeMin": normalizar_iso(fecha_inicio_iso),
            "timeMax": normalizar_iso(fecha_fin_iso),
            "items": [{"id": "primary"}]
        }
        
        freebusy_result = service.freebusy().query(body=body).execute()
        calendars = freebusy_result.get('calendars', {})
        primary_cal = calendars.get('primary', {})
        busy_slots = primary_cal.get('busy', [])
        
        if not busy_slots:
            return f"✅ ¡Todo despejado! No hay conflictos programados en este rango ({fecha_inicio_iso} - {fecha_fin_iso})."
            
        res = [f"⚠️ Cuidado: Hay {len(busy_slots)} espacio(s) Ocupado(s) en este lapso de tiempo:"]
        for b in busy_slots:
            res.append(f"- Desde {b.get('start')} hasta {b.get('end')}")
            
        return "\n".join(res)
    except HttpError as error:
        return f"Ocurrió un error al verificar disponibilidad: {error}"

@tool
def crear_evento_calendario(titulo: str, descripcion: str, fecha_hora_inicio_iso: str, duracion_minutos: int = 60, invitados: list[str] = None, con_meet: bool = False) -> str:
    """
    Crea un nuevo evento en el Google Calendar primario del usuario y opcionalmente invita a otras personas por email.
    También puede crear automáticamente una sala de Google Meet para la reunión.
    
    Args:
        titulo: Título o resumen del evento.
        descripcion: Detalles del evento.
        fecha_hora_inicio_iso: La fecha y hora de inicio en formato ISO 8601 (ej: '2026-03-12T10:00:00-03:00').
        duracion_minutos: Duración del evento en minutos.
        invitados: (Opcional) Una lista de strings con los correos electrónicos de los asistentes (ej: ['juan@ejemplo.com', 'pedro@gmail.com']).
        con_meet: (Opcional) Si es True, genera automáticamente una sala de Google Meet para la reunión.
    Returns:
        Mensaje de éxito con el enlace al evento y, si se solicitó, el link de Google Meet.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        import uuid
        service = build('calendar', 'v3', credentials=creds)
        
        # 1. Normalizar fecha
        fecha_norm = fecha_hora_inicio_iso.replace('Z', '')
        if 'T' not in fecha_norm: fecha_norm += 'T00:00:00'
        if '+' not in fecha_norm and '-' not in fecha_norm.split('T')[1]:
            fecha_norm += '+00:00'
        else:
            # Asegurar formato compatible con fromisoformat
            pass
            
        start_time = datetime.datetime.fromisoformat(fecha_norm)
        end_time = start_time + datetime.timedelta(minutes=duracion_minutos)
        
        event = {
          'summary': titulo,
          'description': descripcion,
          'start': {
            'dateTime': start_time.strftime('%Y-%m-%dT%H:%M:%S%z') or start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'timeZone': 'UTC',
          },
          'end': {
            'dateTime': end_time.strftime('%Y-%m-%dT%H:%M:%S%z') or end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'timeZone': 'UTC',
          },
        }

        if invitados:
            event['attendees'] = [{'email': email.strip()} for email in invitados if email.strip()]

        # Agregar Google Meet si se solicitó
        if con_meet:
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),  # ID único por solicitud
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }

        # conferenceDataVersion=1 es obligatorio para que Calendar genere el Meet
        insert_kwargs = {'calendarId': 'primary', 'body': event, 'sendUpdates': 'all'}
        if con_meet:
            insert_kwargs['conferenceDataVersion'] = 1

        created_event = service.events().insert(**insert_kwargs).execute()
        
        detalle = "con invitados" if invitados else "sin invitados"
        msg = f"Evento creado satisfactoriamente ({detalle}): {created_event.get('htmlLink')}"
        
        # Extraer y devolver el link de Meet si fue generado
        if con_meet:
            conf_data = created_event.get('conferenceData', {})
            entry_points = conf_data.get('entryPoints', [])
            meet_link = next((ep.get('uri') for ep in entry_points if ep.get('entryPointType') == 'video'), None)
            if meet_link:
                msg += f"\n\ud83d� Link de Google Meet: {meet_link}"
            else:
                msg += "\n⚠️ Se solicitó Meet pero no se generó el link. Verifica que la cuenta tenga Google Workspace o Gmail con Meet habilitado."
        
        return msg
        
    except Exception as error:
        return f"Ocurrió un error al crear el evento: {error}"


# ==========================================================
# 📊 GOOGLE SHEETS TOOLS
# ==========================================================

@tool
def leer_hoja_calculo(spreadsheet_id: str, rango: str) -> str:
    """
    Lee datos de un rango específico en un documento de Google Sheets.
    ATENCIÓN: Requiere que el usuario proporcione el ID del spreadsheet (el código alfanumérico largo en la URL).
    
    Args:
        spreadsheet_id: El ID del documento (ej: '1BxiMVs0XRYFgPnUKzG_...').
        rango: El rango A1 a leer (ej: 'Hoja1!A1:E10' o 'Sheet1!A:C').
    Returns:
        Los datos leídos estructurados en filas y columnas separadas por comas.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=rango).execute()
        values = result.get('values', [])

        if not values:
            return f"No se encontraron datos en el rango '{rango}'."

        texto_salida = []
        for row in values:
            texto_salida.append(" | ".join([str(celda) for celda in row]))
            
        return "\\n".join(texto_salida)

    except HttpError as error:
        return f"Ocurrió un error al leer la Hoja de Cálculo: {error}"

@tool
def escribir_hoja_calculo(spreadsheet_id: str, rango: str, valores: list[list[str]]) -> str:
    """
    Añade datos tabulares al final de un documento de Google Sheets en el rango especificado.
    
    Args:
        spreadsheet_id: El ID del documento (de la URL).
        rango: El nombre de la hoja o rango (ej: 'Hoja1').
        valores: Una lista de listas que representa las filas y columnas a insertar. Ej: [['Dato1', 'Dato2'], ['Fila2A', 'Fila2B']].
    Returns:
        Confirmación de cuántas celdas fueron insertadas.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('sheets', 'v4', credentials=creds)
        body = {
            'values': valores
        }
        # Usamos APPEND en vez de simple update para no sobreescribir datos existentes por accidente
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, 
            range=rango,
            valueInputOption="USER_ENTERED", 
            body=body
        ).execute()
        
        updates = result.get('updates')
        if not updates:
             return "No se ha reportado ninguna actualización o inserción. Revisa el rango."
             
        return f"Escritura exitosa. Celdas actualizadas: {updates.get('updatedCells')}"

    except HttpError as error:
        return f"Ocurrió un error al escribir en la Hoja de Cálculo: {error}"

# ==========================================================
# 💬 GOOGLE CHAT TOOLS
# ==========================================================

@tool
def listar_espacios_chat(max_resultados: int = 10) -> str:
    """
    Lista los espacios (salas y mensajes directos) recientes de Google Chat del usuario.
    Si provee detalles, te ayudará a asociar un espacio con una persona.
    
    Args:
        max_resultados: Número máximo de espacios a devolver.
    Returns:
        Una lista en texto con el ID, nombre y tipo de cada espacio.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('chat', 'v1', credentials=creds)
        
        # Call the Chat API
        results = service.spaces().list(pageSize=max_resultados).execute()
        spaces = results.get('spaces', [])

        if not spaces:
            return "No se encontraron espacios en Google Chat."
            
        res = ["Espacios recientes de Google Chat:"]
        for space in spaces:
            space_type = space.get('type', 'UNKNOWN')
            space_id = space.get('name') # Este es el resource name "spaces/AAAA..."
            
            if space_type == 'DIRECT_MESSAGE':
                name = "Mensaje Directo"
                # Intentamos obtener los miembros para dar más contexto al agente
                try:
                    members_result = service.spaces().members().list(parent=space_id).execute()
                    members = members_result.get('memberships', [])
                    member_names = [m.get('member', {}).get('displayName', 'Desconocido') for m in members]
                    name = f"DM con: {', '.join(member_names)}"
                except Exception:
                    pass
            else:
                name = space.get('displayName', 'Sala sin nombre')
                
            res.append(f"- {name} (ID: {space_id}) [Tipo: {space_type}]")
            
        return "\\n".join(res)
        
    except Exception as error:
        return f"Ocurrió un error al leer los espacios de Chat: {error}"

@tool
def leer_mensajes_chat(espacio_id: str, max_resultados: int = 10) -> str:
    """
    Lee los últimos mensajes de un espacio o mensaje directo específico en Google Chat.
    
    Args:
        espacio_id: El ID estricto del espacio obtenido previamente (con formato 'spaces/A1b2C3d4').
        max_resultados: Número máximo de mensajes a devolver.
    Returns:
        Una lista en texto con los remitentes y el contenido de los últimos mensajes.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('chat', 'v1', credentials=creds)
        
        # Call the Chat API to get messages. orderBy='createTime desc' gets newest first
        results = service.spaces().messages().list(
            parent=espacio_id, 
            pageSize=max_resultados,
            orderBy="createTime desc"
        ).execute()
        
        messages = results.get('messages', [])

        if not messages:
            return "No se encontraron mensajes en este espacio."
            
        # Invertimos la lista para que el LLM y el usuario los lean cronológicamente 
        # (de arriba a abajo: del 'más antiguo' del bloque reciente, al 'más nuevo')
        messages = messages[::-1]
            
        res = []
        for msg in messages:
            sender = msg.get('sender', {}).get('displayName', 'Usuario')
            text = msg.get('text', '[Mensaje sin texto o tarjeta]')
            fecha = msg.get('createTime', '')
            res.append(f"[{fecha}] {sender}: {text}")
            
        return "\\n".join(res)
        
    except Exception as error:
        return f"Ocurrió un error al leer los mensajes de Chat: {error}"

@tool
def enviar_mensaje_chat(espacio_id: str, texto: str) -> str:
    """
    Envía un nuevo mensaje de texto a un espacio o mensaje directo específico en Google Chat.
    
    Args:
        espacio_id: El ID estricto del espacio (con formato 'spaces/A1b2C3d4').
        texto: El contenido del mensaje a enviar.
    Returns:
        Mensaje de éxito confirmando el envío.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        import re
        service = build('chat', 'v1', credentials=creds)
        
        texto_formateado = texto
        
        # 1. Saltos de linea literales generados por JSON/LLM a reales
        texto_formateado = texto_formateado.replace('\\n', '\n')
        
        # 2. Markdown Bold: **texto** -> *texto* (Formato nativo de negrita en Google Chat)
        from re import sub
        texto_formateado = sub(r'\*\*(.*?)\*\*', r'*\1*', texto_formateado)
        
        # 3. Markdown Italic: _texto_ -> _texto_ (Formato nativo de cursiva en Google Chat)
        # Eliminamos el reemplazo a HTML <i> para aprovechar el render nativo de Google Chat
        
        # 4. Markdown Strikethrough: ~~texto~~ -> ~texto~ (Formato nativo de tachado)
        texto_formateado = sub(r'~~(.*?)~~', r'~\1~', texto_formateado)
        
        # 5. Código en línea: `codigo` -> `codigo` (Ya funciona nativamente de esta manera)
        
        # 6. Enlaces Markdown: [Texto](http://url) -> <http://url|Texto>
        texto_formateado = sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', texto_formateado)
        
        # Call the Chat API to create a message
        message_body = {'text': texto_formateado}
        result = service.spaces().messages().create(
            parent=espacio_id,
            body=message_body
        ).execute()

        msg_name = result.get('name', 'Desconocido')
        return f"Mensaje enviado con éxito al espacio {espacio_id} (ID del mensaje: {msg_name})."
        
    except Exception as error:
        return f"Ocurrió un error al enviar el mensaje por Chat: {error}"

@tool
def buscar_chat_directo(email: str) -> str:
    """
    Busca o crea el espacio de Mensaje Directo (DM) con un usuario específico usando su correo electrónico.
    Útil cuando necesitas leer o enviar un mensaje a un usuario y NO aparece en los espacios recientes.
    
    Args:
        email: El correo electrónico exacto de la persona (ej. 'juan@ejemplo.com').
    Returns:
        El ID del espacio (ej. 'spaces/AAAA...') para utilizar en las funciones de leer o enviar mensajes.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('chat', 'v1', credentials=creds)
        user_name = f"users/{email}"
        
        # 1. Intentamos buscar el mensaje directo
        try:
            space = service.spaces().findDirectMessage(name=user_name).execute()
            space_id = space.get('name')
            return f"Chat directo encontrado. ID del espacio: {space_id}"
        except HttpError as err:
            if err.resp.status == 404:
                # 2. Si no existe, intentamos crearlo con 'setup'
                body = {
                    "space": {"spaceType": "DIRECT_MESSAGE"},
                    "memberships": [{"member": {"name": user_name}}]
                }
                new_space = service.spaces().setup(body=body).execute()
                space_id = new_space.get('name')
                return f"Nuevo chat directo creado. ID del espacio: {space_id}"
            else:
                return f"Ocurrió un error de red al buscar el chat: {err}"
                
    except Exception as error:
        return f"Ocurrió un error general al buscar o crear el chat directo: {error}"


# ==========================================================
# 📄 GOOGLE DRIVE & DOCS TOOLS
# ==========================================================

@tool
def leer_google_doc(url_o_id: str) -> str:
    """
    Lee y extrae el contenido completo de texto de un Google Doc (Documento de Google).
    Acepta tanto la URL completa del documento como solo el ID del documento.

    Args:
        url_o_id: La URL completa del Google Doc (ej: 'https://docs.google.com/document/d/1PqsyZ.../edit')
                  o directamente el ID del documento (ej: '1PqsyZVise1jBU8B7UPchy-yW4EbKi9-Ssj1wCir_gYo').
    Returns:
        El contenido completo del documento en texto plano.
    """
    import re as _re
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google. Dile al usuario que revise sus credenciales."

    # Extraer el ID si se pasó una URL completa
    doc_id = url_o_id.strip()
    url_match = _re.search(r'/document/d/([a-zA-Z0-9_-]+)', doc_id)
    if url_match:
        doc_id = url_match.group(1)

    try:
        # Usamos Drive API para exportar el Doc como texto plano (más simple y robusto que Docs API)
        drive_service = build('drive', 'v3', credentials=creds)
        content = drive_service.files().export(
            fileId=doc_id,
            mimeType='text/plain'
        ).execute()

        texto = content.decode('utf-8') if isinstance(content, bytes) else str(content)

        if not texto.strip():
            return "El documento está vacío o no tiene contenido de texto."

        # Limitar a ~50k caracteres para no saturar el contexto del LLM
        if len(texto) > 50000:
            texto = texto[:50000] + "\n\n...[Documento truncado: demasiado largo para mostrar completo]"

        return f"📄 Contenido del Google Doc (ID: {doc_id}):\n\n{texto}"

    except HttpError as error:
        if error.resp.status == 404:
            return f"Error 404: No se encontró el documento con ID '{doc_id}'. Verifica que el ID sea correcto y que tengas acceso."
        elif error.resp.status == 403:
            return f"Error 403: No tienes permisos para leer este documento, o la cuenta no está autorizada para acceder a Google Drive."
        return f"Ocurrió un error de la API al leer el Google Doc: {error}"
    except Exception as error:
        return f"Ocurrió un error inesperado al leer el Google Doc: {error}"


@tool
def buscar_archivos_drive(nombre: str, max_resultados: int = 10) -> str:
    """
    Busca archivos en Google Drive del usuario por nombre parcial o completo.
    Útil cuando el usuario no sabe el ID del documento y necesita encontrarlo.

    Args:
        nombre: Texto o nombre parcial del archivo a buscar (ej: 'contrato', 'informe enero').
        max_resultados: Máximo de resultados a mostrar (por defecto 10).
    Returns:
        Una lista de archivos encontrados con su nombre, tipo e ID.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        drive_service = build('drive', 'v3', credentials=creds)

        query = f"name contains '{nombre}' and trashed = false"
        results = drive_service.files().list(
            q=query,
            pageSize=max_resultados,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)"
        ).execute()

        files = results.get('files', [])

        if not files:
            return f"No se encontraron archivos con el nombre '{nombre}' en Google Drive."

        tipo_map = {
            'application/vnd.google-apps.document': '📄 Google Doc',
            'application/vnd.google-apps.spreadsheet': '📊 Google Sheets',
            'application/vnd.google-apps.presentation': '📑 Google Slides',
            'application/vnd.google-apps.folder': '📁 Carpeta',
            'application/pdf': '📕 PDF',
        }

        lineas = [f"Archivos encontrados en Google Drive (búsqueda: '{nombre}'):"]
        for f in files:
            tipo = tipo_map.get(f.get('mimeType', ''), f.get('mimeType', 'Archivo'))
            lineas.append(
                f"- {tipo}: {f['name']}\n"
                f"  ID: {f['id']}\n"
                f"  Modificado: {f.get('modifiedTime', 'N/A')}\n"
                f"  Enlace: {f.get('webViewLink', 'N/A')}"
            )

        return "\n".join(lineas)

    except HttpError as error:
        return f"Ocurrió un error al buscar en Google Drive: {error}"
    except Exception as error:
        return f"Ocurrió un error inesperado al buscar en Google Drive: {error}"

@tool
def crear_google_doc(titulo: str, contenido: str) -> str:
    """
    Crea un nuevo documento de texto en Google Docs con el título y contenido especificados.
    Útil para redactar actas, reportes, notas y resúmenes largos.
    
    Args:
        titulo: El título del documento (ej. 'Resumen de la semana').
        contenido: El texto inicial a insertar en el documento.
    Returns:
        Un mensaje de confirmación con el link directo para editar/ver.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        docs_service = build('docs', 'v1', credentials=creds)
        # 1. Crear documento vacío
        doc = docs_service.documents().create(body={'title': titulo}).execute()
        doc_id = doc['documentId']
        
        # 2. Insertar texto si se provee
        if contenido and contenido.strip():
            contenido = contenido.replace('\\n', '\n')
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': 1,
                        },
                        'text': contenido
                    }
                }
            ]
            docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
            
        return f"Documento creado exitosamente en tu Google Drive.\nTítulo: '{titulo}'\nURL: https://docs.google.com/document/d/{doc_id}/edit"
        
    except HttpError as error:
        return f"Ocurrió un error de la API al crear el documento: {error}"
    except Exception as error:
        return f"Ocurrió un error inesperado al crear el documento: {error}"
