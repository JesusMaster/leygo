# -*- coding: utf-8 -*-
from langchain_core.tools import tool
from pathlib import Path
from dotenv import load_dotenv

# --- Carga de Entorno ---
# Carga inicial para asegurar que las variables esten disponibles a nivel de modulo.
_agent_dir = Path(__file__).parent
load_dotenv(_agent_dir / ".env", override=False)


# --- Definicion de Herramientas ---
# Las herramientas se definen a nivel de modulo para cumplir con las reglas de diseno.

@tool
def calculate_tod_distance(
    cruise_altitude_ft: int,
    target_altitude_ft: int
) -> str:
    """
    Calcula la distancia en Millas Nauticas (NM) para iniciar el Top of Descent (TOD)
    utilizando la regla estandar de 3 grados.
    """
    if cruise_altitude_ft <= target_altitude_ft:
        return "Error: La altitud de crucero debe ser mayor que la altitud objetivo."

    altitude_to_lose_ft = cruise_altitude_ft - target_altitude_ft
    # La regla 3:1 establece que por cada 3 NM de distancia horizontal, se descienden 1000 pies.
    distance_nm = (altitude_to_lose_ft / 1000) * 3
    return f"Para un descenso de 3 grados, el Top of Descent (TOD) debe iniciarse a {distance_nm:.2f} Millas Nauticas del objetivo."

@tool
def calculate_required_descent_rate(
    ground_speed_knots: int
) -> str:
    """
    Calcula el regimen de descenso requerido (en Pies por Minuto, FPM) para mantener
    una senda de descenso de 3 grados, basado en la velocidad sobre el terreno (Ground Speed).
    """
    if ground_speed_knots <= 0:
        return "Error: La velocidad sobre el terreno debe ser positiva."

    # Formula rapida: Ground Speed (knots) * 5
    required_rate_fpm = ground_speed_knots * 5
    return f"Para mantener una senda de 3 grados a {ground_speed_knots} nudos, se requiere un regimen de descenso de aproximadamente {required_rate_fpm:.0f} pies por minuto (FPM)."

@tool
def convert_aviation_units(
    value: float,
    from_unit: str,
    to_unit: str
) -> str:
    """
    Convierte entre diferentes unidades metricas e imperiales usadas en aviacion.
    Unidades soportadas:
    - Distancia: 'ft' (pies), 'm' (metros), 'nm' (millas nauticas), 'km' (kilometros)
    - Velocidad: 'knots' (nudos), 'kmh' (kilometros por hora), 'mph' (millas por hora)
    - Altitud: 'fl' (flight level, en centenas de pies) a 'ft' o 'm'
    Soporta TODAS las combinaciones entre unidades del mismo tipo.
    """
    from_u = from_unit.lower().strip()
    to_u = to_unit.lower().strip()

    if from_u == to_u:
        return f"{value} {from_unit} equivale a {value:.2f} {to_unit} (misma unidad)."

    # Factores de conversion a unidad base (metros para distancia, km/h para velocidad)
    distance_to_meters = {
        'ft': 0.3048,
        'm': 1.0,
        'km': 1000.0,
        'nm': 1852.0,
        'fl': 0.3048 * 100,  # 1 FL = 100 ft
    }

    speed_to_kmh = {
        'knots': 1.852,
        'kn': 1.852,
        'kmh': 1.0,
        'km/h': 1.0,
        'mph': 1.60934,
    }

    # Intentar conversion de distancia
    if from_u in distance_to_meters and to_u in distance_to_meters:
        value_in_meters = value * distance_to_meters[from_u]
        result = value_in_meters / distance_to_meters[to_u]
        return f"{value} {from_unit} equivale a {result:.4f} {to_unit}."

    # Intentar conversion de velocidad
    if from_u in speed_to_kmh and to_u in speed_to_kmh:
        value_in_kmh = value * speed_to_kmh[from_u]
        result = value_in_kmh / speed_to_kmh[to_u]
        return f"{value} {from_unit} equivale a {result:.4f} {to_unit}."

    all_units = list(distance_to_meters.keys()) + list(speed_to_kmh.keys())
    return f"Error: No se puede convertir '{from_unit}' a '{to_unit}'. Unidades soportadas: {', '.join(all_units)}. No se puede mezclar distancia con velocidad."


# --- Clase del Agente ---
from agent_core.sub_agents.base import BaseSubAgent

class NamiAgent(BaseSubAgent):
    """
    Agente especializado en calculos y conocimientos de aviacion.
    """
    @property
    def name(self) -> str:
        return "nami"

    @property
    def description(self) -> str:
        return "Tu copiloto experta en aviacion. Realiza calculos de vuelo, conversiones y responde preguntas tecnicas sobre procedimientos aereos."

    def get_tools(self, all_available_tools: list = None):
        # Carga de .env con override para capturar cambios en caliente.
        load_dotenv(_agent_dir / ".env", override=True)
        # Retorna las herramientas definidas a nivel de modulo.
        return [
            calculate_tod_distance,
            calculate_required_descent_rate,
            convert_aviation_units
        ]

    def get_system_prompt(self) -> str:
        # El prompt se carga desde el archivo de memoria procedimental.
        try:
            with open(_agent_dir / "memoria/memoria_procedimental.md", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "Eres Nami, una experta en aviacion. Tu rol es asistir con calculos y conocimientos de vuelo."
