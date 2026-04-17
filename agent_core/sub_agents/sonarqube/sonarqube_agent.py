import os
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Callable
from langchain_core.tools import tool
from agent_core.sub_agents.base import BaseSubAgent

# Cargar .env del agente al importar el modulo
_agent_dir = Path(__file__).parent
load_dotenv(_agent_dir / ".env", override=False)


def _get_sonar_client():
    """Retorna (url, headers) para llamadas a la API de SonarQube."""
    url = os.getenv("SONARQUBE_URL", "").rstrip("/")
    token = os.getenv("SONARQUBE_TOKEN", "")
    if not url or not token:
        raise ValueError("SONARQUBE_URL o SONARQUBE_TOKEN no configurados en el .env del agente.")
    headers = {"Authorization": f"Bearer {token}"}
    return url, headers


@tool
def listar_proyectos_sonarqube(filtro: str = "") -> str:
    """
    Lista todos los proyectos disponibles en SonarQube.
    Opcionalmente filtra por nombre parcial.

    Args:
        filtro: Texto opcional para filtrar proyectos por nombre (ej. 'api', 'backend').

    Returns:
        Lista de proyectos con su key, nombre y fecha de ultimo analisis.
    """
    try:
        url, headers = _get_sonar_client()
        params = {"ps": 50}
        if filtro:
            params["q"] = filtro
        resp = requests.get(f"{url}/api/components/search", params={"qualifiers": "TRK", **params}, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        componentes = data.get("components", [])
        if not componentes:
            return "No se encontraron proyectos en SonarQube."
        lineas = ["Proyectos en SonarQube:"]
        for c in componentes:
            lineas.append(f"- [{c.get('key')}] {c.get('name')} (ultimo analisis: {c.get('lastAnalysisDate', 'Sin analisis')})")
        return "\n".join(lineas)
    except Exception as e:
        return f"Error al listar proyectos: {e}"


@tool
def obtener_estado_quality_gate(project_key: str) -> str:
    """
    Obtiene el estado del Quality Gate de un proyecto en SonarQube.

    Args:
        project_key: La clave unica del proyecto (ej. 'mi-organizacion_mi-backend').

    Returns:
        Estado del Quality Gate (OK o ERROR) con detalles de condiciones fallidas.
    """
    try:
        url, headers = _get_sonar_client()
        resp = requests.get(
            f"{url}/api/qualitygates/project_status",
            params={"projectKey": project_key},
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json().get("projectStatus", {})
        estado = data.get("status", "UNKNOWN")
        condiciones = data.get("conditions", [])

        lineas = [f"Quality Gate de '{project_key}': **{estado}**"]
        fallidas = [c for c in condiciones if c.get("status") == "ERROR"]
        if fallidas:
            lineas.append("\nCondiciones FALLIDAS:")
            for c in fallidas:
                lineas.append(f"  - {c.get('metricKey')}: actual={c.get('actualValue')} (umbral={c.get('errorThreshold')})")
        else:
            lineas.append("Todas las condiciones del Quality Gate fueron satisfechas.")
        return "\n".join(lineas)
    except Exception as e:
        return f"Error al obtener Quality Gate de '{project_key}': {e}"


@tool
def obtener_metricas_proyecto(project_key: str) -> str:
    """
    Obtiene las metricas clave de calidad de un proyecto: bugs, vulnerabilidades,
    code smells, cobertura de tests y deuda tecnica.

    Args:
        project_key: La clave unica del proyecto en SonarQube.

    Returns:
        Reporte de metricas de calidad del proyecto.
    """
    METRICAS = [
        "bugs", "vulnerabilities", "code_smells",
        "coverage", "duplicated_lines_density",
        "ncloc", "sqale_index", "reliability_rating", "security_rating"
    ]
    try:
        url, headers = _get_sonar_client()
        resp = requests.get(
            f"{url}/api/measures/component",
            params={"component": project_key, "metricKeys": ",".join(METRICAS)},
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        medidas = {m["metric"]: m.get("value", "N/A") for m in data.get("component", {}).get("measures", [])}

        ETIQUETAS = {
            "bugs": "Bugs", "vulnerabilities": "Vulnerabilidades",
            "code_smells": "Code Smells", "coverage": "Cobertura de Tests (%)",
            "duplicated_lines_density": "Codigo Duplicado (%)", "ncloc": "Lineas de Codigo",
            "sqale_index": "Deuda Tecnica (min)", "reliability_rating": "Rating Fiabilidad",
            "security_rating": "Rating Seguridad"
        }

        lineas = [f"Metricas de '{project_key}':"]
        for key, label in ETIQUETAS.items():
            lineas.append(f"  - {label}: {medidas.get(key, 'N/A')}")
        return "\n".join(lineas)
    except Exception as e:
        return f"Error al obtener metricas de '{project_key}': {e}"


@tool
def obtener_issues_criticos(project_key: str, severidad: str = "CRITICAL") -> str:
    """
    Lista los issues (bugs, vulnerabilidades) mas criticos de un proyecto.

    Args:
        project_key: La clave unica del proyecto en SonarQube.
        severidad: Nivel de severidad a filtrar: BLOCKER, CRITICAL, MAJOR, MINOR, INFO. Default: CRITICAL.

    Returns:
        Lista de los issues mas importantes con descripcion y ubicacion en el codigo.
    """
    try:
        url, headers = _get_sonar_client()
        resp = requests.get(
            f"{url}/api/issues/search",
            params={"componentKeys": project_key, "severities": severidad.upper(), "ps": 10, "resolved": "false"},
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])
        if not issues:
            return f"No hay issues de severidad {severidad} en '{project_key}'. Buen trabajo!"
        lineas = [f"Issues {severidad} en '{project_key}' ({len(issues)} encontrados):"]
        for issue in issues:
            comp = issue.get("component", "?").split(":")[-1]
            linea = issue.get("line", "?")
            msg = issue.get("message", "Sin descripcion")
            lineas.append(f"  [{issue.get('type')}] {comp}:L{linea} — {msg}")
        return "\n".join(lineas)
    except Exception as e:
        return f"Error al obtener issues de '{project_key}': {e}"


class SonarqubeAgent(BaseSubAgent):

    @property
    def name(self) -> str:
        return "sonarqube"

    @property
    def description(self) -> str:
        return (
            "Especialista en SonarQube: analiza calidad de codigo, consulta el estado del Quality Gate, "
            "reporta metricas (bugs, vulnerabilidades, deuda tecnica, cobertura) y lista issues criticos "
            "de proyectos en el servidor de SonarQube de la organizacion."
        )

    def get_tools(self, all_available_tools: list = None) -> List[Callable]:
        # Recargar .env en caliente para capturar cambios de credenciales
        load_dotenv(_agent_dir / ".env", override=True)
        return [
            listar_proyectos_sonarqube,
            obtener_estado_quality_gate,
            obtener_metricas_proyecto,
            obtener_issues_criticos,
        ]
