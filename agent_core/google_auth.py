import os
import sys
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Scopes habilitados para tener acceso completo
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/chat.spaces',
    'https://www.googleapis.com/auth/chat.messages'
]

CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys', 'credentials.json')
TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys', 'token.pickle')

def get_google_credentials():
    """Confirma si hay credenciales válidas; de lo contrario abre navegador para auth y las guarda."""
    creds = None
    
    # 1. Chequear si ya nos logueamos antes
    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            print(f"Warning: No se pudo leer el token de acceso. {e}")
            creds = None

    # 2. Refrescar token expirado, o pedir login totalmente nuevo si no existe / falló
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("=> Refrescando el token de acceso de Google expirado de fondo...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Warning: el token falló en refrescarse. Se requerirá un re-login. Error: {e}")
                creds = None
                
        if not creds:
            print("\\n============================== ATENCIÓN REQUERIDA ==============================")
            print("  El Agente necesita acceder a tus APIs de Google (Mail, Calendar, Sheets).")
            print("  Se abrirá automáticamente una ventana en tu navegador por única vez.")
            print("  Por favor, aprueba el acceso para generar el token de autorización.")
            print("=================================================================================\\n")
            
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"Error Crítico: No se encontró el archivo {CREDENTIALS_PATH}.")
                print("Por favor, sigue las instrucciones del Agente para obtener tu OAuth client ID de Google Cloud.")
                sys.exit(1)
                
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                # Como Google desaconseja OOB ahora y requiere localhost estricto
                # si el user no añadió http://localhost, le forzamos un puerto exacto manejable
                # O permitimos que ponga el código manual si la librería lo soporta
                # El puerto 8080 es estándar para authorized redirect uris ("http://localhost:8080/")
                print(">>> Asegúrate de que http://localhost:8080/ está en las URI autorizadas en Google Cloud <<<")
                creds = flow.run_local_server(port=8080, prompt='consent')
            except Exception as e:
                print(f"\\nError crítico obteniendo acceso: {e}")
                print("No se podrá usar las habilidades de Google por el momento.")
                return None

        # Guardar las credenciales para la próxima ejecución
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
            print("=> Autenticación con Google finalizada. Token guardado en agent_core/keys/token.pickle")
            
    return creds

if __name__ == "__main__":
    print("Test de flujo inicial de Autenticación de Google:")
    creds = get_google_credentials()
    if creds:
        print("Test existoso. Se cuenta con credenciales activas.")
