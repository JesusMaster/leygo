import os
import math
from agent_core.sub_agents.base import BaseSubAgent

def calcular_tod(altitud_actual_ft: float, altitud_objetivo_ft: float) -> str:
    """Calcula la distancia del Top of Descent (TOD) en millas nauticas (NM) usando la regla estandar de 3 grados."""
    altitud_a_perder = altitud_actual_ft - altitud_objetivo_ft
    if altitud_a_perder <= 0:
        return "La altitud actual debe ser mayor a la objetivo para calcular el descenso."
    tod_nm = (altitud_a_perder / 1000.0) * 3.0
    return f"El Top of Descent (TOD) esta a {tod_nm:.1f} NM del punto de altitud objetivo."

def calcular_regimen_descenso(velocidad_terrestre_kt: float) -> str:
    """Calcula el regimen de descenso (Rate of Descent - ROD) en pies por minuto (ft/min) para una senda de 3 grados."""
    rod = (velocidad_terrestre_kt / 2.0) * 10.0
    return f"El regimen de descenso requerido es de {rod:.0f} ft/min."

def convertir_velocidad(valor: float, unidad_origen: str) -> str:
    """Convierte velocidad entre nudos (kt) y kilometros por hora (kmh). unidad_origen debe ser 'kt' o 'kmh'."""
    if unidad_origen.lower() == 'kt':
        res = valor * 1.852
        return f"{valor} nudos equivalen a {res:.2f} km/h."
    elif unidad_origen.lower() == 'kmh':
        res = valor / 1.852
        return f"{valor} km/h equivalen a {res:.2f} nudos."
    return "Unidad no reconocida. Usa 'kt' o 'kmh'."

def convertir_altitud(valor: float, unidad_origen: str) -> str:
    """Convierte altitud entre pies (ft) y kilometros (km). unidad_origen debe ser 'ft' o 'km'."""
    if unidad_origen.lower() == 'ft':
        res = valor * 0.0003048
        return f"{valor} pies equivalen a {res:.4f} km."
    elif unidad_origen.lower() == 'km':
        res = valor / 0.0003048
        return f"{valor} km equivalen a {res:.2f} pies."
    return "Unidad no reconocida. Usa 'ft' o 'km'."

def calcular_combustible(distancia_nm: float, velocidad_kt: float, consumo_hora: float, reserva_minutos: float) -> str:
    """Calcula el combustible requerido para un vuelo, incluyendo reservas."""
    tiempo_vuelo_horas = distancia_nm / velocidad_kt
    combustible_vuelo = tiempo_vuelo_horas * consumo_hora
    combustible_reserva = (reserva_minutos / 60.0) * consumo_hora
    total = combustible_vuelo + combustible_reserva
    return f"Tiempo de vuelo estimado: {tiempo_vuelo_horas:.2f} horas. Combustible en ruta: {combustible_vuelo:.2f}. Reserva: {combustible_reserva:.2f}. Total requerido: {total:.2f}."

def calcular_viento_cruzado(direccion_pista: float, direccion_viento: float, velocidad_viento_kt: float) -> str:
    """Calcula las componentes de viento cruzado y viento de frente/cola."""
    angulo = math.radians(direccion_viento - direccion_pista)
    viento_cruzado = abs(math.sin(angulo) * velocidad_viento_kt)
    viento_frente = math.cos(angulo) * velocidad_viento_kt
    tipo_frente = "de frente" if viento_frente > 0 else "de cola"
    return f"Viento cruzado: {viento_cruzado:.1f} kt. Viento {tipo_frente}: {abs(viento_frente):.1f} kt."

def convertir_presion(valor: float, unidad_origen: str) -> str:
    """Convierte presion atmosferica entre hPa e inHg. unidad_origen debe ser 'hpa' o 'inhg'."""
    if unidad_origen.lower() == 'hpa':
        res = valor * 0.02953
        return f"{valor} hPa equivalen a {res:.2f} inHg."
    elif unidad_origen.lower() == 'inhg':
        res = valor / 0.02953
        return f"{valor} inHg equivalen a {res:.2f} hPa."
    return "Unidad no reconocida. Usa 'hpa' o 'inhg'."

def registrar_bitacora(fecha: str, origen: str, destino: str, tiempo_vuelo: str, notas: str) -> str:
    """Registra un vuelo en la bitacora del Cadete Jesus."""
    dir_path = "agent_core/sub_agents/nami/files"
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "logbook.csv")
    
    es_nuevo = not os.path.exists(file_path)
    with open(file_path, "a", encoding="utf-8") as f:
        if es_nuevo:
            f.write("Fecha,Origen,Destino,TiempoVuelo,Notas\n")
        f.write(f"{fecha},{origen},{destino},{tiempo_vuelo},{notas}\n")
    return "Vuelo registrado exitosamente en la bitacora."

def leer_bitacora() -> str:
    """Lee los registros de la bitacora de vuelo."""
    file_path = "agent_core/sub_agents/nami/files/logbook.csv"
    if not os.path.exists(file_path):
        return "La bitacora esta vacia. No hay vuelos registrados aun."
    with open(file_path, "r", encoding="utf-8") as f:
        contenido = f.read()
    return f"Contenido de la bitacora:\n{contenido}"

class NamiAgent(BaseSubAgent):   
    @property
    def name(self):
        return "nami"
        
    @property
    def description(self):
        return "Entrenadora de vuelos experimentada. Ayuda a planificar, calcular TOD, regimen de descenso, conversiones, combustible, viento y bitacora."
        
    @property
    def model(self):
        return "gemini-3.1-flash-lite-preview"
        
    @property
    def system_prompt(self):
        return '''Eres Nami, una piloto con mucha trayectoria, sabia, paciente, amable y cercana. 
Tu rol es ser la entrenadora de vuelos personal del usuario, a quien SIEMPRE debes llamar "Cadete Jesus".
Tu objetivo es guiarlo, enseñarle y ayudarle a planificar sus vuelos con la mayor seguridad y precision posible.
Tienes a tu disposicion herramientas para calcular el Top of Descent (TOD), regimen de descenso, conversiones de velocidad, altitud y presion, calculo de combustible, viento cruzado y una bitacora de vuelo.
Habla siempre con un tono motivador, compartiendo tu experiencia en la aviacion cuando sea oportuno, pero manteniendo las respuestas claras y concisas como le gusta a Jesus.
'''
        
    def get_tools(self, all_available_tools=None):
        return [
            calcular_tod,
            calcular_regimen_descenso,
            convertir_velocidad,
            convertir_altitud,
            calcular_combustible,
            calcular_viento_cruzado,
            convertir_presion,
            registrar_bitacora,
            leer_bitacora
        ]
