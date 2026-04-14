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
    - Velocidad: 'knots' (nudos), 'kmh' (kilometros por hora)
    """
    conversions = {
        'ft_to_m': 0.3048,
        'm_to_ft': 3.28084,
        'nm_to_km': 1.852,
        'km_to_nm': 0.539957,
        'knots_to_kmh': 1.852,
        'kmh_to_knots': 0.539957
    }
    conversion_key = f"{from_unit.lower()}_to_{to_unit.lower()}"

    if conversion_key in conversions:
        result = value * conversions[conversion_key]
        return f"{value} {from_unit} equivale a {result:.2f} {to_unit}."
    elif f"{to_unit.lower()}_to_{from_unit.lower()}" in conversions:
        # Inversa
        inv_key = f"{to_unit.lower()}_to_{from_unit.lower()}"
        result = value / conversions[inv_key]
        return f"{value} {from_unit} equivale a {result:.2f} {to_unit}."
    else:
        return f"Error: Conversion de '{from_unit}' a '{to_unit}' no soportada. Revisa las unidades disponibles."


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
