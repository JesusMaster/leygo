import os
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

# Instanciar el wrapper subyacente de langchain
wrapper = DuckDuckGoSearchAPIWrapper(region="wt-wt", time="y", max_results=5)
search = DuckDuckGoSearchRun(api_wrapper=wrapper)

@tool
def buscar_en_internet(query: str) -> str:
    """
    Herramienta nativa para buscar información en internet (DuckDuckGo).
    Úsala SIEMPRE que necesites obtener información en tiempo real, investigar sobre el clima de una zona,
    obtener definiciones, leer documentación de una API, o resolver cualquier duda factica 
    antes de intentar crear código.
    
    Args:
        query: La frase o pregunta a buscar en el motor de búsqueda (ej. "Clima hoy en Madrid" o "Documentacion API exchange rate").
        
    Returns:
        Un string largo con snippets de las mejores webs encontradas.
    """
    print(f"\\n[WebSearch] Buscando en internet: '{query}'...")
    try:
        resultado = search.invoke(query)
        if not resultado:
            return "No se encontraron resultados para la búsqueda."
        return resultado
    except Exception as e:
        return f"Error al realizar la búsqueda web: {str(e)}"
