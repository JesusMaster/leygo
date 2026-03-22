import os
import json
import urllib.request
import urllib.error
import base64
import uuid
from agent_core.sub_agents.base import BaseSubAgent

class NanobananaAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "nanobanana"

    @property
    def description(self) -> str:
        return "Agente especializado en generar imágenes a partir de ideas o prompts usando el modelo gemini-3-pro-image-preview."

    @property
    def system_prompt(self) -> str:
        return "Eres Nanobanana, un experto en crear prompts visuales y generar imágenes. Recibes ideas del usuario, las optimizas y usas tu herramienta para generar la imagen. IMPORTANTE: La herramienta ahora devuelve una URL pública de la imagen. SIEMPRE muéstrala al usuario usando formato Markdown para imágenes: ![Descripción](URL_PUBLICA) para que la interfaz la renderice correctamente."

    @property
    def model(self) -> str:
        return "gemini-3-pro-image-preview"

    def get_tools(self, all_available_tools: list = None) -> list:
        def generar_imagen_nanobanana(prompt: str) -> str:
            '''
            Genera una imagen usando el modelo gemini-3-pro-image-preview y la sube a un host público para su visualización.
            Args:
                prompt: El prompt detallado para la imagen.
            '''
            try:
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if not api_key:
                    return "Error: No se encontró la clave de API (GEMINI_API_KEY o GOOGLE_API_KEY)."

                model_name = "gemini-3-pro-image-preview"
                url = f"https://generativelanguage.googleapis.com/v1alpha/models/{model_name}:generateContent?key={api_key}"

                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseModalities": ["IMAGE"]
                    }
                }

                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

                with urllib.request.urlopen(req) as response:
                    response_data = response.read().decode('utf-8')
                    response_json = json.loads(response_data)
                    
                    try:
                        part = response_json['candidates'][0]['content']['parts'][0]
                        if 'inlineData' in part:
                            b64_data = part['inlineData']['data']
                            image_bytes = base64.b64decode(b64_data)
                            
                            save_dir = os.path.join("agent_core", "sub_agents", "nanobanana", "files")
                            os.makedirs(save_dir, exist_ok=True)
                            
                            filename = f"imagen_{uuid.uuid4().hex[:8]}.jpg"
                            filepath = os.path.join(save_dir, filename)
                            
                            with open(filepath, 'wb') as f:
                                f.write(image_bytes)
                            
                            # Subir a catbox.moe para obtener URL pública
                            catbox_url = "https://catbox.moe/user/api.php"
                            boundary = uuid.uuid4().hex
                            headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
                            
                            mimetype = 'image/jpeg'
                            body = (
                                f"--{boundary}\r\n"
                                f"Content-Disposition: form-data; name=\"reqtype\"\r\n\r\n"
                                f"fileupload\r\n"
                                f"--{boundary}\r\n"
                                f"Content-Disposition: form-data; name=\"fileToUpload\"; filename=\"{filename}\"\r\n"
                                f"Content-Type: {mimetype}\r\n\r\n"
                            ).encode('utf-8') + image_bytes + f"\r\n--{boundary}--\r\n".encode('utf-8')
                            
                            upload_req = urllib.request.Request(catbox_url, data=body, headers=headers)
                            try:
                                with urllib.request.urlopen(upload_req) as upload_resp:
                                    public_url = upload_resp.read().decode('utf-8')
                                    return f"Imagen generada exitosamente.\n\n![Imagen generada]({public_url})\n\nRuta local: {filepath}\nURL Pública: {public_url}"
                            except Exception as upload_err:
                                return f"Imagen generada y guardada en {filepath}, pero falló la subida pública: {str(upload_err)}"
                                
                        else:
                            return "Error: La respuesta no contiene 'inlineData'. Respuesta completa: " + json.dumps(response_json)
                    except KeyError as e:
                        return f"Error al parsear la respuesta JSON (falta la clave {e}): {json.dumps(response_json)}"

            except urllib.error.HTTPError as e:
                error_msg = e.read().decode('utf-8')
                return f"HTTP Error {e.code}: {error_msg}"
            except Exception as e:
                return f"Error inesperado: {str(e)}"
                
        return [generar_imagen_nanobanana]
