from typing import List, Callable
from ..base import BaseSubAgent
import os
import csv
import json

def registrar_comida(fecha: str, comida: str, calorias: int) -> str:
    """Registra una comida con sus calorias en el archivo de seguimiento."""
    folder = "agent_core/sub_agents/fitness/files"
    if not os.path.exists(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "registro_comidas.csv")
    existe = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["fecha", "comida", "calorias"])
        w.writerow([fecha, comida, calorias])
    return f"Comida registrada: {comida} ({calorias} kcal) el {fecha}."

def registrar_peso(fecha: str, peso: float) -> str:
    """Registra el peso corporal en el archivo de seguimiento."""
    folder = "agent_core/sub_agents/fitness/files"
    if not os.path.exists(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "registro_peso.csv")
    existe = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["fecha", "peso"])
        w.writerow([fecha, peso])
    return f"Peso registrado: {peso} kg el {fecha}."

def registrar_perfil_biometrico(estatura_cm: float, edad: int) -> str:
    """Registra la estatura en cm y la edad del usuario."""
    folder = "agent_core/sub_agents/fitness/files"
    if not os.path.exists(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "perfil.json")
    perfil = {"estatura_cm": estatura_cm, "edad": edad}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(perfil, f)
    return f"Perfil actualizado: Estatura {estatura_cm} cm, Edad {edad} años."

def obtener_analisis_imc() -> str:
    """Calcula el IMC y proporciona un analisis basado en el ultimo peso registrado."""
    folder = "agent_core/sub_agents/fitness/files"
    perfil_path = os.path.join(folder, "perfil.json")
    peso_path = os.path.join(folder, "registro_peso.csv")
    
    if not os.path.exists(perfil_path):
        return "Error: No se ha registrado la estatura. Usa registrar_perfil_biometrico."
    if not os.path.exists(peso_path):
        return "Error: No se ha registrado ningun peso."
        
    with open(perfil_path, "r") as f:
        perfil = json.load(f)
    
    ultimo_peso = 0.0
    with open(peso_path, "r") as f:
        reader = csv.reader(f, delimiter=",")
        rows = list(reader)
        if len(rows) > 1:
            ultimo_peso = float(rows[-1][1])
        else:
            return "Error: No hay datos de peso suficientes."
            
    estatura_m = perfil["estatura_cm"] / 100
    imc = ultimo_peso / (estatura_m ** 2)
    
    # Rangos IMC
    if imc < 18.5: estado = "Bajo peso"
    elif 18.5 <= imc < 25: estado = "Peso saludable"
    elif 25 <= imc < 30: estado = "Sobrepeso"
    else: estado = "Obesidad"
    
    # Peso ideal (rango saludable 18.5 - 24.9)
    peso_min = 18.5 * (estatura_m ** 2)
    peso_max = 24.9 * (estatura_m ** 2)
    
    analisis = f"Tu IMC actual es {imc:.2f} ({estado}).\n"
    analisis += f"Rango de peso saludable para tu estatura: {peso_min:.1f} kg - {peso_max:.1f} kg.\n"
    
    if ultimo_peso > peso_max:
        exceso = ultimo_peso - peso_max
        porcentaje = (exceso / peso_max) * 100
        analisis += f"Estas {exceso:.1f} kg por encima del limite superior ({porcentaje:.1f}% de exceso)."
    elif ultimo_peso < peso_min:
        falta = peso_min - ultimo_peso
        porcentaje = (falta / peso_min) * 100
        analisis += f"Estas {falta:.1f} kg por debajo del limite inferior ({porcentaje:.1f}% de carencia)."
    else:
        analisis += "¡Estas en un rango de peso saludable!"
        
    return analisis

class FitnessAgent(BaseSubAgent):
    @property
    def model(self): return "gemini-3.1-flash-lite-preview"
    @property
    def name(self): return "fitness"
    @property
    def description(self): return "Experto en nutricion y entrenamiento personal (Mario). Registra comidas, peso y da consejos."
    @property
    def system_prompt(self): return "Eres Mario, un experto en nutricion y personal trainer. Tu objetivo es ayudar al usuario a llevar un registro de su salud y motivarlo con consejos profesionales."
    def get_tools(self, all_available_tools):
        tools = [registrar_comida, registrar_peso, registrar_perfil_biometrico, obtener_analisis_imc]
        for t in all_available_tools:
            if getattr(t, "name", None) == "buscar_en_internet":
                tools.append(t)
        return tools
