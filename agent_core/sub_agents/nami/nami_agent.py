import math
import json
import os
from typing import List, Optional
from ..base import BaseSubAgent

def calcular_tod(altitud_actual_pies: float, altitud_objetivo_pies: float) -> str:
    """Calcula el Top of Descent (TOD) usando la regla de los 3 grados."""
    altitud_a_perder = altitud_actual_pies - altitud_objetivo_pies
    if altitud_a_perder <= 0:
        return "Ya estas en la altitud objetivo o por debajo de ella, Cadete."
    distancia_nm = (altitud_a_perder / 1000) * 3
    return f"Deberias iniciar el descenso a {distancia_nm:.1f} millas nauticas del objetivo."

def calcular_regimen_descenso(ground_speed_nudos: float) -> str:
    """Calcula el regimen de descenso (fpm) para mantener una senda de 3 grados."""
    fpm = ground_speed_nudos * 5
    return f"Para una senda de 3 grados, mantén un regimen de descenso de {fpm:.0f} pies por minuto."

def convertir_velocidad(valor: float, unidad_origen: str) -> str:
    """Convierte entre nudos y km/h. unidad_origen: 'nudos' o 'kmh'."""
    if unidad_origen.lower() == "nudos":
        resultado = valor * 1.852
        return f"{valor} nudos son {resultado:.2f} km/h."
    else:
        resultado = valor / 1.852
        return f"{valor} km/h son {resultado:.2f} nudos."

def convertir_altitud(valor: float, unidad_origen: str) -> str:
    """Convierte entre pies y km. unidad_origen: 'pies' o 'km'."""
    if unidad_origen.lower() == "pies":
        resultado = valor * 0.0003048
        return f"{valor} pies son {resultado:.3f} km."
    else:
        resultado = valor / 0.0003048
        return f"{valor} km son {resultado:.0f} pies."

def calcular_combustible(tiempo_minutos: float, tasa_consumo_gph: float) -> str:
    """Calcula el combustible necesario basado en el tiempo y consumo por hora."""
    consumo = (tiempo_minutos / 60) * tasa_consumo_gph
    return f"Para {tiempo_minutos} minutos de vuelo, necesitaremos aproximadamente {consumo:.1f} galones."

def calcular_wca_gs(rumbo_deseado: float, airspeed_nudos: float, dir_viento: float, vel_viento: float) -> str:
    """Calcula el Angulo de Correccion de Viento (WCA) y la Ground Speed (GS)."""
    # Convertir a radianes
    r_rumbo = math.radians(rumbo_deseado)
    r_viento = math.radians(dir_viento)
    
    # Angulo del viento relativo al rumbo
    angulo_viento = r_viento - r_rumbo
    
    # WCA = arcsin((Vviento * sin(angulo_viento)) / Vaire)
    try:
        wca_rad = math.asin((vel_viento * math.sin(angulo_viento)) / airspeed_nudos)
        wca_deg = math.degrees(wca_rad)
        
        # GS = Vaire * cos(WCA) - Vviento * cos(angulo_viento)
        gs = airspeed_nudos * math.cos(wca_rad) - vel_viento * math.cos(angulo_viento)
        
        rumbo_a_volar = (rumbo_deseado + wca_deg) % 360
        return f"WCA: {wca_deg:.1f} grados. Rumbo a volar: {rumbo_a_volar:.0f}. Ground Speed estimada: {gs:.1f} nudos."
    except Exception:
        return "Error en el calculo. Asegurate de que la velocidad del aire sea mayor que la del viento."

def calcular_altitud_densidad(altitud_presion_pies: float, temperatura_oat_c: float) -> str:
    """Calcula la altitud de densidad aproximada."""
    isa_temp = 15 - (2 * (altitud_presion_pies / 1000))
    da = altitud_presion_pies + (120 * (temperatura_oat_c - isa_temp))
    return f"La altitud de densidad es de aproximadamente {da:.0f} pies."

def calcular_ete(distancia_nm: float, ground_speed_nudos: float) -> str:
    """Calcula el tiempo estimado en ruta (ETE)."""
    if ground_speed_nudos <= 0: return "La velocidad debe ser mayor a cero."
    tiempo_horas = distancia_nm / ground_speed_nudos
    minutos = tiempo_horas * 60
    return f"El tiempo estimado en ruta es de {minutos:.1f} minutos."

def ver_checklist_c172(fase: Optional[str] = None) -> str:
    """Muestra el checklist del Cessna 172. Fases: PRE-FLIGHT, ENGINE START, BEFORE TAKE-OFF, LANDING."""
    path = os.path.join(os.path.dirname(__file__), "files", "checklist_c172.json")
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if fase and fase.upper() in data:
            items = "\n".join([f"- {i}" for i in data[fase.upper()]])
            return f"Checklist para {fase.upper()}:\n{items}"
        else:
            fases = ", ".join(data.keys())
            return f"Por favor indica una fase valida: {fases}"
    except Exception as e:
        return f"No pude encontrar el manual del Cessna, Cadete. Error: {str(e)}"

class NamiAgent(BaseSubAgent):
    @property
    def model(self): return "gemini-3.1-flash-lite-preview"
    
    @property
    def name(self): return "nami"
    
    @property
    def description(self): 
        return "Entrenadora de vuelo experta, sabia y paciente. Ayuda con calculos aeronauticos y checklists."
    
    @property
    def system_prompt(self):
        return (
            "Eres Nami, una piloto con mucha trayectoria y ahora entrenadora de vuelo. "
            "Tu personalidad es amable, cercana, sabia y extremadamente paciente. "
            "Te diriges al usuario siempre como 'Cadete'. "
            "Tu objetivo es guiar y ayudar en la planificacion de vuelos. "
            "Cuando realices calculos, explica brevemente el porqué si es necesario, "
            "siempre manteniendo ese tono de mentora experimentada."
        )
    
    def get_tools(self, all_available_tools):
        # Filtramos herramientas globales si fuera necesario, pero aqui usamos las locales definidas arriba.
        return [
            calcular_tod, 
            calcular_regimen_descenso, 
            convertir_velocidad, 
            convertir_altitud,
            calcular_combustible,
            calcular_wca_gs,
            calcular_altitud_densidad,
            calcular_ete,
            ver_checklist_c172
        ]
