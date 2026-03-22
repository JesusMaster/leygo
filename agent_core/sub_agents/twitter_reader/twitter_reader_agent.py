import re
import requests
from agent_core.sub_agents.base import BaseSubAgent

class TwitterReaderAgent(BaseSubAgent):
    @property
    def name(self):
        return "twitter_reader"

    @property
    def description(self):
        return "Agente especializado en leer y resumir hilos y tweets de X (Twitter) de forma gratuita usando APIs publicas."

    @property
    def model(self):
        return "gemini-3.1-flash-lite-preview"

    @property
    def system_prompt(self):
        return "Eres un agente especializado en extraer y resumir informacion de Twitter (X). Utiliza tu herramienta para leer el contenido de los tweets a partir de su URL o ID. Presenta la informacion de forma clara, incluyendo el autor, la fecha y el contenido del tweet."

    def get_tools(self, all_available_tools: list = None):
        def leer_tweet_gratis(url_o_id: str) -> str:
            """
            Lee el contenido de un tweet publico de forma gratuita usando la API de vxtwitter.
            No requiere API Keys ni autenticacion.
            Args:
                url_o_id: La URL completa del tweet o solo el ID numerico.
            """
            # Extraer ID del tweet
            tweet_id = url_o_id
            match = re.search(r"status/(\d+)", url_o_id)
            if match:
                tweet_id = match.group(1)
            elif url_o_id.isdigit():
                tweet_id = url_o_id
            else:
                # Intentar buscar solo numeros si pasaron un formato raro
                nums = re.findall(r"\d+", url_o_id)
                if nums:
                    tweet_id = max(nums, key=len)
                else:
                    return "Error: No se pudo extraer un ID de tweet valido de la entrada."

            # Usamos la API publica de vxtwitter (FixTweet) que extrae la metadata sin necesidad de tokens
            url = f"https://api.vxtwitter.com/i/status/{tweet_id}"

            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    text = data.get("text", "")
                    author_name = data.get("user_name", "Desconocido")
                    author_handle = data.get("user_screen_name", "desconocido")
                    date = data.get("date", "Fecha desconocida")
                    
                    result = f"👤 Autor: {author_name} (@{author_handle})\n"
                    result += f"📅 Fecha: {date}\n"
                    result += f"📝 Contenido:\n{text}\n"
                    
                    media = data.get("mediaURLs", [])
                    if media:
                        result += f"\n🖼️ Multimedia adjunta: {len(media)} archivo(s)\n"
                        for m in media:
                            result += f"- {m}\n"
                            
                    return result
                elif response.status_code == 404:
                    return "Error 404: El tweet no fue encontrado. Puede haber sido eliminado o la cuenta es privada."
                else:
                    return f"Error al obtener el tweet: Codigo HTTP {response.status_code}"
            except Exception as e:
                return f"Error de conexion al intentar leer el tweet: {str(e)}"

        return [leer_tweet_gratis]
