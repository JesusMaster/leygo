import os
import google.generativeai as genai

async def transcribir_audio(ruta_archivo: str) -> str:
    """
    Sube un archivo de audio a Gemini y obtiene exclusivamente la transcripción.
    """
    if not os.path.exists(ruta_archivo):
        return f"Error: El archivo {ruta_archivo} no existe."

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return "Error: GOOGLE_API_KEY no configurada."

    try:
        genai.configure(api_key=api_key)
        model_name = "gemini-3.1-flash-lite-preview"
        
        # Subir archivo
        audio_file = genai.upload_file(path=ruta_archivo)
        model = genai.GenerativeModel(model_name=model_name)
        
        # Pedir solo la transcripción literal
        prompt = "Transcribe este audio de forma literal, sin añadir comentarios, resúmenes ni introducciones. Solo el texto hablado."
        response = model.generate_content([prompt, audio_file])
        return response.text.strip()
    except Exception as e:
        print(f"Error en transcribir_audio: {e}")
        return ""
