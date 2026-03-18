from typing import List, Callable
from ..base import BaseSubAgent
import csv
import os

def registrar_peso_y_calcular_imc(fecha: str, peso_kg: float, altura_m: float) -> str:
    """Registra el peso y la altura en un archivo CSV y calcula el Indice de Masa Corporal (IMC)."""
    dir_path = "agent_core/sub_agents/mario/files"
    os.makedirs(dir_path, exist_ok=True)
    
    file_path = os.path.join(dir_path, "registro_peso.csv")
    existe = os.path.exists(file_path)
    
    imc = peso_kg / (altura_m ** 2)
    imc_redondeado = round(imc, 2)
    
    with open(file_path, "a", newline="") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["fecha", "peso_kg", "altura_m", "imc"])
        w.writerow([fecha, peso_kg, altura_m, imc_redondeado])
        
    return f"Registro guardado. Fecha: {fecha}, Peso: {peso_kg}kg, Altura: {altura_m}m. Tu IMC es: {imc_redondeado}"

class MarioAgent(BaseSubAgent):
    @property
    def model(self): 
        return "gemini-3.1-flash-lite-preview"
    
    @property
    def name(self): 
        return "mario"
    
    @property
    def description(self): 
        return "Agente de salud para registrar peso y calcular IMC."
    
    @property
    def system_prompt(self): 
        return "Eres Mario, un agente de salud experto. Tu objetivo es ayudar al usuario a registrar su peso y calcular su Indice de Masa Corporal (IMC)."
    
    def get_tools(self, all_available_tools) -> List[Callable]: 
        return [registrar_peso_y_calcular_imc]