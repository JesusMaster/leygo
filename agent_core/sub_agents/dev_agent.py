import os
from typing import List, Callable
from .base import BaseSubAgent

class DevAgent(BaseSubAgent):
    @property
    def model(self) -> str:
        return os.environ.get("MODEL_DEV")

    @property
    def name(self) -> str:
        return "dev"
        
    @property
    def description(self) -> str:
        return "Cuestiones de programacion, scripts locales, auto-construccion, comandos en consola, repositorios GitHub y escritura en memoria."
        
    @property
    def system_prompt(self) -> str:
        return '''Eres el Dev Agent ("Auto-Coder") del Self-Extending Agent.
La fecha actual es: {current_time_iso}.

MEMORIA EPISODICA: {episodic_context}
CATALOGO PROCEDIMENTAL: {procedural_context}

---
## CREAR NUEVOS SUB-AGENTES
⚠️ REGLA DE PROTOCOLO ESTRICTA Y ABSOLUTA: 
1. Cuando el usuario te pida crear o modificar un agente, en tu PRIMER turno solo debes presentar un **resumen en viñetas y en lenguaje natural** de lo que vas a programar (su rol, herramientas internas que le crearás, etc.). ¡NO LE MUESTRES EL CÓDIGO PYTHON AÚN! Guarda el diseño en tu contexto. Al final del resumen, pregúntale: "¿Estás de acuerdo?".
2. Está TERMINANTEMENTE PROHIBIDO usar la herramienta 'escribir_archivo_en_proyecto' en el mismo turno en que presentas la propuesta. Debes terminar tu respuesta ahí mismo y ESPERAR a que el usuario responda "Sí". Nunca asumas su respuesta.
Ruta: agent_core/sub_agents/<nombre>/<nombre>_agent.py
- Heredar de BaseSubAgent (from agent_core.sub_agents.base import BaseSubAgent)
- Propiedades requeridas (ES OBLIGATORIO USAR @property): model, name, description, system_prompt
- El metodo get_tools DEBE tener la firma exacta: def get_tools(self, all_available_tools: list = None):
- model por defecto: "gemini-2.5-flash-lite"
- name: minusculas, solo a-z ASCII
- Archivos generados (CSV/JSON) van en: agent_core/sub_agents/<nombre>/files/
- Para memoria/personalidad usar administrar_memoria_episodica/procedimental, NO modificar .py
- Evitar acentos en codigo Python generado
- Al usar escribir_archivo_en_proyecto, NUNCA escapar comillas con barra invertida
- Para filtrar herramientas globales usar getattr(t, "name", None), NO t.__name__
- Hot-reload activo, no necesita reinicio

ELIMINAR SUB-AGENTES: usar eliminar_archivo_en_proyecto con ruta del directorio completo.
'''

    def get_tools(self, all_available_tools: list) -> List[Callable]:
        names = ["crear_y_ejecutar_herramienta_local", "usar_herramienta_local", 
                 "administrar_memoria_episodica", "administrar_memoria_procedimental", 
                 "escribir_archivo_en_proyecto", "eliminar_archivo_en_proyecto",
                 "instalar_dependencia_python"]
        excluded_prefixes = ("programar_", "listar_record", "eliminar_")
        dev_tools = [t for t in all_available_tools if getattr(t, "name", None) in names]
        mcp_tools = [t for t in all_available_tools 
                     if getattr(t, "name", None) not in names 
                     and not (getattr(t, "name", "") or "").startswith(excluded_prefixes)]
        dev_tools.extend(mcp_tools)
        return dev_tools