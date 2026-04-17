import os
import concurrent.futures
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

# Instanciar el wrapper subyacente de langchain
wrapper = DuckDuckGoSearchAPIWrapper(region="wt-wt", time="y", max_results=5)
search = DuckDuckGoSearchRun(api_wrapper=wrapper)

# Timeout máximo en segundos para cada búsqueda web
WEB_SEARCH_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "20"))

def _invoke_search(query: str) -> str:
    """Ejecuta la búsqueda sincrona en un thread pool para aplicar timeout."""
    resultado = search.invoke(query)
    return resultado if resultado else "No se encontraron resultados para la búsqueda."

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke_search, query)
            try:
                return future.result(timeout=WEB_SEARCH_TIMEOUT)
            except concurrent.futures.TimeoutError:
                print(f"[WebSearch] Timeout ({WEB_SEARCH_TIMEOUT}s) alcanzado para: '{query}'")
                return (
                    f"La búsqueda web tomó demasiado tiempo (>{WEB_SEARCH_TIMEOUT}s) y fue cancelada. "
                    "Puede ser que DuckDuckGo esté temporalmente bloqueando peticiones. "
                    "Intenta reformular la búsqueda o usa el conocimiento propio para continuar."
                )
    except Exception as e:
        return f"Error al realizar la búsqueda web: {str(e)}"
