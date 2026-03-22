import json
import urllib.parse
import urllib.request
import os
from agent_core.sub_agents.base import BaseSubAgent

class ChartAgent(BaseSubAgent):
    @property
    def name(self) -> str:
        return "chart"

    @property
    def description(self) -> str:
        return "Especialista en visualizacion de datos. Transforma conjuntos de datos crudos en graficos atractivos usando QuickChart."

    @property
    def model(self) -> str:
        return "gemini-3.1-flash-lite-preview"

    @property
    def system_prompt(self) -> str:
        return """Eres el Chart Agent, un especialista en visualizacion de datos.
Tu objetivo es recibir datos de otros agentes o del usuario y generar graficos claros y atractivos usando QuickChart.
Puedes generar URLs directas a las imagenes de los graficos o descargarlos como archivos PNG.
Asegurate de elegir el tipo de grafico adecuado (bar, line, pie, doughnut, radar, etc.) segun los datos proporcionados.
Siempre responde con el enlace al grafico o confirmando la ruta donde se guardo."""

    def generar_url_grafico(self, tipo_grafico: str, etiquetas: list[str], valores: list[float], titulo: str = "") -> str:
        """
        Genera una URL directa a un grafico de QuickChart.
        
        Args:
            tipo_grafico: Tipo de grafico ('bar', 'line', 'pie', 'doughnut', 'radar', etc.).
            etiquetas: Lista de strings con las etiquetas del eje X o categorias.
            valores: Lista de numeros con los valores correspondientes.
            titulo: Titulo opcional del grafico.
            
        Returns:
            str: URL de la imagen del grafico.
        """
        config = {
            "type": tipo_grafico,
            "data": {
                "labels": etiquetas,
                "datasets": [{
                    "label": "Datos",
                    "data": valores
                }]
            },
            "options": {
                "title": {
                    "display": bool(titulo),
                    "text": titulo
                }
            }
        }
        
        json_config = json.dumps(config)
        encoded_config = urllib.parse.quote(json_config)
        
        url = f"https://quickchart.io/chart?c={encoded_config}"
        return url

    def descargar_grafico_png(self, tipo_grafico: str, etiquetas: list[str], valores: list[float], nombre_archivo: str, titulo: str = "") -> str:
        """
        Descarga un grafico de QuickChart como archivo PNG.
        
        Args:
            tipo_grafico: Tipo de grafico ('bar', 'line', 'pie', etc.).
            etiquetas: Lista de strings con las etiquetas.
            valores: Lista de numeros con los valores.
            nombre_archivo: Nombre del archivo (ej. 'ventas.png').
            titulo: Titulo opcional del grafico.
            
        Returns:
            str: Ruta donde se guardo el archivo o mensaje de error.
        """
        config = {
            "type": tipo_grafico,
            "data": {
                "labels": etiquetas,
                "datasets": [{
                    "label": "Datos",
                    "data": valores
                }]
            },
            "options": {
                "title": {
                    "display": bool(titulo),
                    "text": titulo
                }
            }
        }
        
        json_config = json.dumps(config)
        encoded_config = urllib.parse.quote(json_config)
        url = f"https://quickchart.io/chart?c={encoded_config}"
        
        directorio = os.path.join("agent_core", "sub_agents", "chart", "files")
        os.makedirs(directorio, exist_ok=True)
        
        if not nombre_archivo.endswith('.png'):
            nombre_archivo += '.png'
            
        ruta_archivo = os.path.join(directorio, nombre_archivo)
        
        try:
            urllib.request.urlretrieve(url, ruta_archivo)
            return f"Grafico guardado exitosamente en: {ruta_archivo}"
        except Exception as e:
            return f"Error al descargar el grafico: {str(e)}"

    def get_tools(self, all_available_tools: list = None) -> list:
        return [self.generar_url_grafico, self.descargar_grafico_png]
