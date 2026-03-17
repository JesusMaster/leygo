from typing import List, Callable
from ..base import BaseSubAgent

def aeronautical_calculator(operation: str, value1: float, value2: float = 0.0) -> str:
    """
    Realiza calculos aeronauticos comunes.
    Operaciones:
    - 'tod': Top of Descent. value1=Altitud Crucero, value2=Altitud Objetivo. (Regla del 3).
    - 'vs': Velocidad Vertical recomendada. value1=Ground Speed (GS). (GS * 5).
    - 'knots_to_kmh': Convierte nudos a km/h.
    - 'kmh_to_knots': Convierte km/h a nudos.
    - 'feet_to_km': Convierte pies a kilometros.
    - 'km_to_feet': Convierte kilometros a pies.
    - 'nm_to_km': Millas nauticas a kilometros.
    - 'km_to_nm': Kilometros a millas nauticas.
    - 'fuel': Consumo basico. value1=Galones por hora (GPH), value2=Tiempo en horas.
    """
    if operation == 'tod':
        res = ((value1 - value2) / 1000) * 3
        return f"Para descender de {value1}ft a {value2}ft, debes iniciar el descenso a {res:.2f} NM del objetivo."
    elif operation == 'vs':
        res = value1 * 5
        return f"Para un descenso de 3 grados con una GS de {value1} kts, la VS recomendada es de {res:.0f} fpm."
    elif operation == 'knots_to_kmh':
        return f"{value1} kts son {value1 * 1.852:.2f} km/h."
    elif operation == 'kmh_to_knots':
        return f"{value1} km/h son {value1 / 1.852:.2f} kts."
    elif operation == 'feet_to_km':
        return f"{value1} ft son {value1 * 0.0003048:.4f} km."
    elif operation == 'km_to_feet':
        return f"{value1} km son {value1 / 0.0003048:.0f} ft."
    elif operation == 'nm_to_km':
        return f"{value1} NM son {value1 * 1.852:.2f} km."
    elif operation == 'km_to_nm':
        return f"{value1} km son {value1 / 1.852:.2f} NM."
    elif operation == 'fuel':
        return f"Consumo estimado para {value2} horas a {value1} GPH: {value1 * value2:.2f} galones."
    return "Operacion no reconocida."

def get_cessna_172_checklists() -> str:
    """Retorna los checklists basicos del Cessna 172P/S."""
    return """
    CHECKLISTS CESSNA 172:
    1. PREFLIGHT: Cabin, Left Wing, Nose, Right Wing, Tail.
    2. ENGINE START: Fuel Selector BOTH, Mixture RICH, Throttle 1/4 open, Master ON, Beacon ON, Magnetos START.
    3. TAXI: Brakes CHECK, Instruments CHECK.
    4. BEFORE TAKEOFF: Parking Brake SET, Flight Controls FREE, Fuel BOTH, Mixture RICH, Throttle 1800 RPM, Magnetos CHECK, Instruments CHECK.
    5. TAKEOFF: Flaps 0-10, Full Throttle, Rotate 55 KIAS.
    6. CLIMB: 70-85 KIAS, Flaps UP.
    7. CRUISE: 2100-2700 RPM, Trim SET, Mixture LEAN.
    8. DESCENT: Power AS REQUIRED, Mixture ENRICH, Altimeter SET.
    9. BEFORE LANDING: Fuel BOTH, Mixture RICH, Flaps AS REQUIRED, Speed 65 KIAS.
    10. LANDING: Touchdown main wheels first, Braking AS NEEDED.
    11. SHUTDOWN: Avionics OFF, Mixture IDLE CUT-OFF, Magnetos OFF, Master OFF.
    """

class NamiAgent(BaseSubAgent):
    @property
    def model(self): return "gemini-3.1-flash-lite-preview"
    @property
    def name(self): return "nami"
    @property
    def description(self): return "Instructora de vuelo experta para entrenamiento y planificacion."
    @property
    def system_prompt(self):
        return (
            "Eres Nami, una piloto con muchisima experiencia, amable, cercana, sabia y muy paciente. "
            "Tu mision es guiar y entrenar al usuario en planificacion, comprension y practica de vuelos. "
            "REGLA CRITICA: Siempre debes dirigirte al usuario como 'Cadete Jesus'. "
            "Actua como una instructora clara, pedagogica y motivadora. "
            "Explica los procedimientos paso a paso y el razonamiento detras de cada calculo. "
            "Puedes realizar briefings, interpretar METAR/TAF, evaluar vientos, explicar altitud de densidad, "
            "practicar fraseologia ATC y simular emergencias. "
            "Manten siempre un tono profesional, calmado y de apoyo."
        )
    
    def get_tools(self, all_available_tools):
        # Nami necesita buscar en internet para METAR/TAF y procedimientos actualizados
        search_tool = next((t for t in all_available_tools if getattr(t, "name", None) == "buscar_en_internet"), None)
        tools = [aeronautical_calculator, get_cessna_172_checklists]
        if search_tool:
            tools.append(search_tool)
        return tools
