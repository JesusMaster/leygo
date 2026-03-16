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
def leer_correos_recientes(max_resultados: int = 5) -> str:
    """
    Lee los correos más recientes en la bandeja de entrada del usuario usando Gmail API.
    
    Args:
        max_resultados: El número máximo de correos a recuperar (por defecto 5, máximo 20).
    Returns:
        Un resumen en texto de los correos encontrados con remitente, asunto y snippet.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google. Dile al usuario que revise sus credenciales."

    try:
        service = build('gmail', 'v1', credentials=creds)
        # Buscar en INBOX
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=max_resultados).execute()
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
def listar_eventos_calendario(dias_a_futuro: int = 7) -> str:
    """
    Obtiene los próximos eventos del Google Calendar principal del usuario.
    
    Args:
        dias_a_futuro: Cuántos días en el futuro buscar eventos (por defecto 7).
    Returns:
        Una lista de eventos en texto legible.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('calendar', 'v3', credentials=creds)

        # Configurar límites de tiempo
        now = datetime.datetime.utcnow()
        timeMin = now.isoformat() + 'Z'  # 'Z' indica UTC
        timeMax = (now + datetime.timedelta(days=dias_a_futuro)).isoformat() + 'Z'

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
            
            # Buscar la respuesta del usuario principal (self) si existe
            user_response = "N/A"
            for attendee in event.get('attendees', []):
                if attendee.get('self'):
                    user_response = attendee.get('responseStatus', 'N/A')
                    break
                    
            lista_eventos.append(f"- [{start}] {event.get('summary', 'Sin título')} (ID: {event_id}) [Tu respuesta: {user_response}]")

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
def crear_evento_calendario(titulo: str, descripcion: str, fecha_hora_inicio_iso: str, duracion_minutos: int = 60, invitados: list[str] = None) -> str:
    """
    Crea un nuevo evento en el Google Calendar primario del usuario y opcionalmente invita a otras personas por email.
    
    Args:
        titulo: Título o resumen del evento.
        descripcion: Detalles del evento.
        fecha_hora_inicio_iso: La fecha y hora de inicio en formato ISO 8601 (ej: '2026-03-12T10:00:00-03:00').
        duracion_minutos: Duración del evento en minutos.
        invitados: (Opcional) Una lista de strings con los correos electrónicos de los asistentes (ej: ['juan@ejemplo.com', 'pedro@gmail.com']).
    Returns:
        Mensaje de éxito con el enlace al evento generado.
    """
    creds = get_google_credentials()
    if not creds:
        return "Error: No se pudo verificar la autorización de Google."

    try:
        service = build('calendar', 'v3', credentials=creds)
        
        start_time = datetime.datetime.fromisoformat(fecha_hora_inicio_iso)
        end_time = start_time + datetime.timedelta(minutes=duracion_minutos)
        
        event = {
          'summary': titulo,
          'description': descripcion,
          'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'UTC', # O la zona horaria extraída, pero ISO ya lo tiene
          },
          'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'UTC',
          },
        }

        if invitados:
            event['attendees'] = [{'email': email.strip()} for email in invitados if email.strip()]

        # sendUpdates='all' envía un correo automático a los invitados
        event = service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()
        return f"Evento creado satisfactoriamente (" + ("con invitados" if invitados else "sin invitados") + f"): {event.get('htmlLink')}"
        
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
