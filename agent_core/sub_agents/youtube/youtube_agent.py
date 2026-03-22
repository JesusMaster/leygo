import os
import re
import tempfile
from agent_core.sub_agents.base import BaseSubAgent

# Ruta donde el usuario puede colocar sus cookies de YouTube exportadas
COOKIES_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'keys', 'youtube_cookies.txt')
COOKIES_PATH = os.path.normpath(COOKIES_PATH)


def _extraer_via_ytdlp(url: str, tmpdir: str) -> str | None:
    """Intenta extraer subtítulos con yt-dlp. Retorna texto o None si falla."""
    try:
        import yt_dlp
        import webvtt
    except ImportError:
        return None

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['es', 'es-419', 'en', 'en-US'],
        'subtitlesformat': 'vtt',
        'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    }

    # Si existen cookies de YouTube, las usamos para evitar bloqueos de datacenter
    if os.path.exists(COOKIES_PATH):
        ydl_opts['cookiefile'] = COOKIES_PATH
        print(f"🍪 Usando cookies de YouTube desde: {COOKIES_PATH}")
    else:
        print(f"⚠️  No se encontraron cookies de YouTube en {COOKIES_PATH}. "
              "Puede fallar en IPs de datacenter (DigitalOcean, AWS, etc.)")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.extract_info(url, download=True)
            except Exception as e:
                print(f"yt-dlp warning: {e}")

        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith('.vtt')]
        if not vtt_files:
            return None

        # Priorizar español (cualquier variante), luego inglés
        selected_vtt = None
        for lang in ['es', 'es-419', 'en', 'en-US']:
            for f in vtt_files:
                if f".{lang}." in f:
                    selected_vtt = f
                    break
            if selected_vtt:
                break
        if not selected_vtt:
            selected_vtt = vtt_files[0]

        vtt_file = os.path.join(tmpdir, selected_vtt)
        lines = []
        for caption in webvtt.read(vtt_file):
            text = caption.text.strip()
            for line in text.split('\n'):
                line = re.sub(r'<[^>]+>', '', line).strip()
                if line and (not lines or lines[-1] != line):
                    lines.append(line)

        transcript = re.sub(r'\s+', ' ', ' '.join(lines)).strip()
        return transcript if transcript else None

    except Exception as e:
        print(f"yt-dlp error: {e}")
        return None


def _extraer_via_transcript_api(url: str) -> str | None:
    """
    Fallback: usa youtube-transcript-api (sin descargar subtítulos, 
    consulta directamente la API de transcripciones de YouTube).
    Puede funcionar cuando yt-dlp falla en datacenter.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
    except ImportError:
        return None

    # Extraer video ID de la URL
    match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    if not match:
        return None
    video_id = match.group(1)

    try:
        # Intentar en español primero, luego inglés, luego lo que haya
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        transcript = None
        try:
            transcript = transcript_list.find_transcript(['es', 'es-419']).fetch()
        except Exception:
            try:
                transcript = transcript_list.find_transcript(['en', 'en-US']).fetch()
            except Exception:
                # Tomar el primero disponible
                for t in transcript_list:
                    transcript = t.fetch()
                    break

        if not transcript:
            return None

        text = ' '.join([entry['text'] for entry in transcript])
        text = re.sub(r'\s+', ' ', text).strip()
        return text if text else None

    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception as e:
        print(f"youtube-transcript-api error: {e}")
        return None


def extraer_transcripcion_youtube(url: str) -> str:
    """
    Extrae la transcripción de un video de YouTube.
    
    Intenta múltiples estrategias en orden:
    1. yt-dlp con cookies (si existen en agent_core/keys/youtube_cookies.txt)
    2. youtube-transcript-api como fallback (funciona mejor en datacenters)
    
    Para habilitar las cookies: exporta tus cookies de YouTube desde el navegador
    con la extensión 'Get cookies.txt LOCALLY' y guárdalas en:
    agent_core/keys/youtube_cookies.txt
    
    Args:
        url: URL completa del video de YouTube.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Estrategia 1: yt-dlp (con o sin cookies)
        print(f"📹 Estrategia 1: yt-dlp para {url}")
        result = _extraer_via_ytdlp(url, tmpdir)
        if result:
            print(f"✅ Transcripción obtenida via yt-dlp ({len(result)} chars)")
            return result

    # Estrategia 2: youtube-transcript-api
    print("📹 Estrategia 2: youtube-transcript-api")
    result = _extraer_via_transcript_api(url)
    if result:
        print(f"✅ Transcripción obtenida via transcript-api ({len(result)} chars)")
        return result

    return (
        "No se pudo obtener la transcripción del video. Esto ocurre cuando:\n"
        "• El video no tiene subtítulos habilitados.\n"
        "• El servidor está siendo bloqueado por YouTube (IP de datacenter).\n"
        "• Para solucionar el bloqueo: exporta tus cookies de YouTube desde Chrome/Firefox "
        "y guárdalas en 'agent_core/keys/youtube_cookies.txt'."
    )


class YoutubeAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "youtube"

    @property
    def description(self) -> str:
        return "Agente especializado en extraer transcripciones y resumir videos de YouTube."

    @property
    def system_prompt(self) -> str:
        return (
            "Eres un experto analista de contenido audiovisual. Tu objetivo es recibir URLs "
            "de videos de YouTube, extraer su transcripción y generar resúmenes estructurados.\n\n"
            "Cuando el usuario te pida resumir un video:\n"
            "1. Usa la herramienta 'extraer_transcripcion_youtube' con la URL proporcionada.\n"
            "2. Lee atentamente el texto devuelto.\n"
            "3. Genera un resumen estructurado que incluya:\n"
            "   - Tema principal del video.\n"
            "   - Puntos clave o ideas principales (en viñetas).\n"
            "   - Conclusiones o reflexiones finales.\n\n"
            "Si el resultado menciona problemas con cookies o bloqueo de IP, "
            "explícale al usuario cómo exportar sus cookies de YouTube para solucionarlo."
        )

    @property
    def model(self) -> str:
        return "gemini-2.5-flash-lite"

    def get_tools(self, all_available_tools: list = None) -> list:
        return [extraer_transcripcion_youtube]
