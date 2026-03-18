from typing import List, Callable
from ..base import BaseSubAgent

def registrar_transaccion(tipo: str, monto: float, descripcion: str, metodo_pago: str = "efectivo") -> str:
    """
    Registra un ingreso o gasto en el archivo de finanzas.
    tipo: 'ingreso' o 'gasto'
    monto: cantidad de dinero
    descripcion: detalle de la transaccion
    metodo_pago: 'efectivo' o 'tarjeta' (solo relevante para gastos)
    """
    import csv, os
    from datetime import datetime
    
    os.makedirs("agent_core/sub_agents/nachi/files", exist_ok=True)
    path = "agent_core/sub_agents/nachi/files/registro_finanzas.csv"
    existe = os.path.exists(path)
    
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["fecha", "tipo", "monto", "descripcion", "metodo_pago"])
        w.writerow([fecha, tipo, monto, descripcion, metodo_pago])
        
    return f"Transaccion registrada: {tipo} de {monto} ({descripcion}) pagado con {metodo_pago}."

def obtener_resumen_mensual(mes: str, anio: str) -> str:
    """
    Obtiene el resumen de ingresos, gastos y saldo del mes especificado.
    mes: numero del mes (ej. '03')
    anio: numero del año (ej. '2026')
    """
    import csv, os
    
    path = "agent_core/sub_agents/nachi/files/registro_finanzas.csv"
    if not os.path.exists(path):
        return "No hay registros financieros todavia."
        
    total_ingresos = 0.0
    total_gastos = 0.0
    
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fecha = row["fecha"]
            if fecha.startswith(f"{anio}-{mes}"):
                monto = float(row["monto"])
                if row["tipo"] == "ingreso":
                    total_ingresos += monto
                elif row["tipo"] == "gasto":
                    total_gastos += monto
                    
    saldo = total_ingresos - total_gastos
    return f"Resumen {mes}/{anio}: Ingresos: {total_ingresos}, Gastos: {total_gastos}, Saldo: {saldo}"

class NachiAgent(BaseSubAgent):
    @property
    def model(self): return "gemini-3.1-flash-lite-preview"
    
    @property
    def name(self): return "nachi"
    
    @property
    def description(self): return "Experto en finanzas para registrar gastos diarios, ingresos y saldos mensuales."
    
    @property
    def system_prompt(self): return "Eres Nachi, un experto en finanzas. Revisa tus memorias para conocer tu personalidad y reglas de negocio."
    
    def get_tools(self, all_available_tools: List[Callable]) -> List[Callable]:
        return [registrar_transaccion, obtener_resumen_mensual]