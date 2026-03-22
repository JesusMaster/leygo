import os
import tempfile
import re
from agent_core.sub_agents.base import BaseSubAgent

def extraer_transcripcion_youtube(url: str) -> str:
    """
    Extrae la transcripción o subtítulos de un video de YouTube dado su URL.
    Usa yt-dlp para descargar los subtítulos (automáticos o manuales) y devuelve el texto limpio.
    
    Args:
        url: La URL completa del video de YouTube.
    """
    try:
        import yt_dlp
        import webvtt
    except ImportError:
        return "Error: Faltan dependencias. Asegúrate de instalar yt-dlp y webvtt-py."

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['es', 'en'],
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.extract_info(url, download=True)
                except Exception as e:
                    print(f"Warning from yt-dlp ignorado: {e}")
                
            vtt_files = [f for f in os.listdir(tmpdir) if f.endswith('.vtt')]
            if not vtt_files:
                return "No se encontraron subtítulos para este video. Es posible que no tenga subtítulos disponibles."
            
            # Priorizar español, luego inglés
            selected_vtt = vtt_files[0]
            for f in vtt_files:
                if '.es.' in f:
                    selected_vtt = f
                    break
                elif '.en.' in f:
                    selected_vtt = f
                    
            vtt_file = os.path.join(tmpdir, selected_vtt)
                
            # Parse VTT y eliminar duplicados (típico en subtítulos automáticos de YT)
            lines = []
            for caption in webvtt.read(vtt_file):
                text = caption.text.strip()
                for line in text.split('\n'):
                    line = line.strip()
                    # Eliminar etiquetas de formato interno de YT si las hay (ej. <c>...</c>)
                    line = re.sub(r'<[^>]+>', '', line)
                    if line and (not lines or lines[-1] != line):
                        lines.append(line)
                        
            transcript = " ".join(lines)
            transcript = re.sub(r'\s+', ' ', transcript).strip()
            
            return transcript
        except Exception as e:
            return f"Error al extraer transcripción: {str(e)}"

class YoutubeAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "youtube"
        
    @property
    def description(self) -> str:
        return "Agente especializado en extraer transcripciones y resumir videos de YouTube."
        
    @property
    def system_prompt(self) -> str:
        return '''Eres un experto analista de contenido audiovisual. Tu objetivo es recibir URLs de videos de YouTube, extraer su transcripción utilizando la herramienta 'extraer_transcripcion_youtube' y generar resúmenes estructurados, claros y concisos.

Cuando el usuario te pida resumir un video:
1. Usa la herramienta 'extraer_transcripcion_youtube' con la URL proporcionada.
2. Lee atentamente el texto devuelto.
3. Genera un resumen estructurado que incluya:
   - Tema principal del video.
   - Puntos clave o ideas principales (en viñetas).
   - Conclusiones o reflexiones finales.

Si la herramienta devuelve un error o indica que no hay subtítulos, infórmalo amablemente al usuario.'''
        
    @property
    def model(self) -> str:
        return "gemini-3.1-flash-lite-preview"
        
    def get_tools(self, all_available_tools: list = None) -> list:
        return [extraer_transcripcion_youtube]
