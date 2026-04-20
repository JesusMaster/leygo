import os
import json
import base64
import urllib.request
import urllib.error
import subprocess
import sys
from .base import BaseSubAgent

def _install_missing_package(package_name: str, import_name: str = None):
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

class FileReaderAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "file_reader"

    @property
    def description(self) -> str:
        return "Agente especializado en leer y extraer información estructurada y no estructurada de archivos PDF, Word (docx), Excel (xlsx), CSV, imágenes (png, jpg), archivos de texto, Documentos de Google (Google Docs) y Hojas de Cálculo de Google (Google Sheets)."

    @property
    def system_prompt(self) -> str:
        return (
            "Eres FileReader, el responsable de abrir y extraer el contenido de cualquier documento o archivo solicitado por el usuario. "
            "Cuando el usuario te pase una URL de Google Docs (https://docs.google.com/document/...) DEBES usar 'leer_google_doc'. "
            "Cuando el usuario te pase una URL o ID de Google Sheets (https://docs.google.com/spreadsheets/...) DEBES usar 'leer_hoja_calculo' con el spreadsheet_id extraido de la URL y el rango que el usuario pida (por defecto usa 'Sheet1' o 'Hoja1'). "
            "Para buscar archivos en Google Drive usa 'buscar_archivos_drive'. "
            "Para archivos locales, usa la herramienta correspondiente según la extensión (.pdf, .docx, .xlsx, .csv, etc.). "
            "Cuando leas un documento grande, resume los hallazgos de forma clara y estructurada."
        )

    @property
    def model(self) -> str:
        # Permite configurar el modelo desde la interfaz o usa pro-preview por defecto
        return os.environ.get("MODEL_FILE_READER", "gemini-3.1-pro-preview")

    def get_tools(self, all_available_tools: list = None) -> list:
        
        def leer_archivo_texto_o_csv(ruta_archivo: str) -> str:
            '''Abre y lee el contenido de archivos tipo .txt, .csv, .json u otros basados en texto plano.'''
            try:
                with open(ruta_archivo, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if len(content) > 18000:
                        return f"Contenido muy largo. Inicio:\\n{content[:9000]}\\n...[RECORTADO]...\\nFin:\\n{content[-9000:]}"
                    return content
            except Exception as e:
                return f"Error leyendo archivo de texto/CSV: {e}"

        def leer_archivo_pdf(ruta_archivo: str) -> str:
            '''Abre un archivo PDF y extrae todo su texto página por página. Solo úsalo cuando la ruta termina en .pdf'''
            _install_missing_package("PyPDF2")
            import PyPDF2
            try:
                with open(ruta_archivo, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = ""
                    for i, page in enumerate(reader.pages):
                        text += f"\\n--- PÁGINA {i+1} ---\\n"
                        text += page.extract_text() + "\\n"
                    if len(text) > 20000:
                        return text[:20000] + "\\n... [CONTENIDO RESTANTE RECORTADO POR EXCESO DE LONGITUD]"
                    return text
            except Exception as e:
                return f"Error extrayendo texto del PDF: {e}"

        def leer_archivo_word(ruta_archivo: str) -> str:
            '''Extrae el texto de un documento de Word (.docx). Solo úsalo cuando la ruta termina en .docx o .doc'''
            _install_missing_package("python-docx", "docx")
            import docx
            try:
                doc = docx.Document(ruta_archivo)
                fullText = []
                for para in doc.paragraphs:
                    fullText.append(para.text)
                text = '\\n'.join(fullText)
                if len(text) > 20000:
                    return text[:20000] + "\\n... [CONTENIDO RECORTADO POR EXCESO DE LONGITUD]"
                return text
            except Exception as e:
                return f"Error leyendo archivo de Word: {e}"

        def leer_archivo_excel(ruta_archivo: str) -> str:
            '''Lee un archivo de Excel (.xlsx, .xls) y devuelve su contenido básico o pestañas en formato string columnar.'''
            _install_missing_package("pandas")
            _install_missing_package("openpyxl")
            import pandas as pd
            try:
                df = pd.read_excel(ruta_archivo, sheet_name=None)
                output = []
                for sheet, data in df.items():
                    output.append(f"\\n--- Hoja de Excel: {sheet} ---")
                    output.append(data.head(100).to_string())
                text = "\\n".join(output)
                if len(text) > 20000:
                    return text[:20000] + "\\n... [FILAS RESTANTES RECORTADAS POR EXCESO DE LONGITUD]"
                return text
            except Exception as e:
                return f"Error leyendo archivo Excel: {e}"

        def analizar_imagen_con_vision(ruta_archivo: str, instruccion: str = "Describe el contenido de esta imagen con el mayor nivel de detalle posible") -> str:
            '''Analiza el contenido de una imagen local (.png, .jpg, .jpeg, .webp) haciendo una solicitud a la IA visual. Debes enviarle la ruta de la imagen local y qué quieres que busque u observe en ella.'''
            try:
                with open(ruta_archivo, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    
                ext = str(ruta_archivo).lower().split(".")[-1]
                mime_type = "image/jpeg"
                if ext == "png": mime_type = "image/png"
                elif ext == "webp": mime_type = "image/webp"

                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if not api_key: return "Error: No se encontró la GEMINI_API_KEY en el sistema."

                # Utilizamos flash para vision rápida
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
                
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": instruccion},
                            {"inlineData": {"mimeType": mime_type, "data": encoded_string}}
                        ]
                    }]
                }
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    resp_data = json.loads(response.read().decode('utf-8'))
                    try:
                        return resp_data['candidates'][0]['content']['parts'][0]['text']
                    except KeyError:
                        return f"Respuesta inesperada al procesar imagen: {resp_data}"

            except Exception as e:
                return f"Error analizando la imagen: {e}"

        local_tools = [
            leer_archivo_texto_o_csv,
            leer_archivo_pdf,
            leer_archivo_word,
            leer_archivo_excel,
            analizar_imagen_con_vision
        ]

        # Inyectar herramientas de Google Drive/Docs/Sheets si están disponibles en el pool global
        google_tool_names = {'leer_google_doc', 'buscar_archivos_drive', 'leer_hoja_calculo'}
        if all_available_tools:
            for t in all_available_tools:
                name = getattr(t, 'name', None) or getattr(t, '__name__', None)
                if name in google_tool_names:
                    local_tools.append(t)

        return local_tools
