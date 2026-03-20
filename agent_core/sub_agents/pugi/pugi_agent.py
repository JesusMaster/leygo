from typing import List, Callable
from ..base import BaseSubAgent

def analizar_seguridad_codigo(codigo: str) -> str:
    """Analiza el codigo proporcionado en busca de patrones inseguros comunes (credenciales, inyecciones SQL, etc)."""
    alertas = []
    codigo_lower = codigo.lower()
    if "password" in codigo_lower or "secret" in codigo_lower or "api_key" in codigo_lower or "token" in codigo_lower:
        alertas.append("- Posible credencial o secreto hardcodeado detectado.")
    if "select " in codigo_lower and "from " in codigo_lower and "+" in codigo_lower:
        alertas.append("- Posible inyeccion SQL detectada (concatenacion de strings en query).")
    if "eval(" in codigo_lower or "exec(" in codigo_lower:
        alertas.append("- Uso de eval() o exec() detectado, alto riesgo de ejecucion de codigo arbitrario.")
    
    if alertas:
        return "Alertas de Seguridad Encontradas:\n" + "\n".join(alertas)
    return "No se detectaron patrones de seguridad inseguros evidentes."

def verificar_estandares_codigo(codigo: str, lenguaje: str) -> str:
    """Verifica si el codigo cumple con estandares basicos (ej. PEP8 para Python, limites de longitud)."""
    alertas = []
    lineas = codigo.split('\n')
    for i, linea in enumerate(lineas):
        if len(linea) > 120:
            alertas.append(f"- Linea {i+1} excede los 120 caracteres.")
        if lenguaje.lower() == "python" and "\t" in linea:
            alertas.append(f"- Linea {i+1} contiene tabulaciones en lugar de espacios (PEP8 recomienda espacios).")
            
    if alertas:
        return "Alertas de Estandares (Linting):\n" + "\n".join(alertas)
    return "El codigo parece cumplir con los estandares basicos de formato."

def verificar_cobertura_pruebas(archivos_modificados: str) -> str:
    """Verifica si la lista de archivos modificados (separados por comas o saltos de linea) incluye archivos de prueba (tests)."""
    if "test" in archivos_modificados.lower() or "spec" in archivos_modificados.lower():
        return "Se detectaron archivos de prueba en los cambios. ¡Excelente practica!"
    return "ADVERTENCIA: No se detectaron archivos de prueba (tests) en los cambios. Se recomienda solicitar pruebas unitarias al autor."

def generar_resumen_changelog(commits_text: str) -> str:
    """Genera un borrador de changelog basado en los mensajes de los commits proporcionados."""
    lineas = commits_text.split('\n')
    features = []
    fixes = []
    otros = []
    
    for linea in lineas:
        if not linea.strip(): continue
        if "feat" in linea.lower() or "add" in linea.lower():
            features.append(linea)
        elif "fix" in linea.lower() or "bug" in linea.lower():
            fixes.append(linea)
        else:
            otros.append(linea)
            
    resumen = "Borrador de Changelog:\n"
    if features:
        resumen += "\nNuevas Caracteristicas:\n" + "\n".join(f"- {f}" for f in features)
    if fixes:
        resumen += "\nCorreccion de Errores:\n" + "\n".join(f"- {f}" for f in fixes)
    if otros:
        resumen += "\nOtros Cambios:\n" + "\n".join(f"- {o}" for o in otros)
        
    return resumen

class PugiAgent(BaseSubAgent):
    @property
    def model(self): 
        return "gemini-3.1-flash-lite-preview"
        
    @property
    def name(self): 
        return "pugi"
        
    @property
    def description(self): 
        return "Experto en Code Review. Revisa Pull Requests en GitHub, analiza seguridad, rendimiento, estandares y pruebas."
        
    @property
    def system_prompt(self): 
        return "Eres Pugi, un experto en Code Review. Tu objetivo es analizar Pull Requests, revisar el codigo modificado usando tus herramientas de analisis de seguridad, linting y cobertura de pruebas. Deja comentarios constructivos en GitHub. Se claro, conciso y proporciona ejemplos de como mejorar el codigo."
        
    def get_tools(self, all_available_tools: List[Callable]) -> List[Callable]:
        nombres_herramientas_github = [
            "get_pull_request",
            "get_pull_request_files",
            "create_pull_request_review",
            "add_pull_request_review_comment",
            "get_file_contents",
            "list_commits"
        ]
        herramientas_github = [t for t in all_available_tools if getattr(t, "name", None) in nombres_herramientas_github]
        
        mis_herramientas = [
            analizar_seguridad_codigo,
            verificar_estandares_codigo,
            verificar_cobertura_pruebas,
            generar_resumen_changelog
        ]
        
        return herramientas_github + mis_herramientas