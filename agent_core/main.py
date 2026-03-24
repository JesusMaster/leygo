import os
import sys
import asyncio
from typing import Annotated, TypedDict, Literal, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.runnables.config import RunnableConfig
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

# Load ENV before everything
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Import local modules
import memory_utils
from mcp_client import MCPClientManager
from auto_coder import crear_y_ejecutar_herramienta_local, usar_herramienta_local, escribir_archivo_en_proyecto, eliminar_archivo_en_proyecto, instalar_dependencia_python
from web_tools import buscar_en_internet
from scheduler_manager import crear_recordatorio_solo_texto_para_usuario, listar_tareas_programadas, start_scheduler, stop_scheduler, crear_rutina_texto_periodica_para_usuario, eliminar_tarea_programada, agendar_accion_autonoma_agente, agendar_rutina_autonoma_agente
from google_tools import leer_correos_recientes, modificar_etiquetas_correo, enviar_correo, listar_eventos_calendario, responder_evento_calendario, crear_evento_calendario, leer_hoja_calculo, escribir_hoja_calculo, listar_espacios_chat, leer_mensajes_chat, enviar_mensaje_chat, buscar_chat_directo, leer_google_doc, buscar_archivos_drive
MAX_CONTEXT_MESSAGES = 15
MAX_MESSAGE_CHARS = 20000 # ~5000 tokens por mensaje individual como máximo

import status_bus

import logging
import warnings
logging.getLogger("langchain_core.utils.json_schema").setLevel(logging.ERROR)
logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)
warnings.filterwarnings('ignore', category=UserWarning, message='.*is not supported in schema.*')

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next_node: str

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pkgutil
import inspect
import importlib
from pydantic import create_model
from agent_core.sub_agents.base import BaseSubAgent

def discover_sub_agents() -> List[BaseSubAgent]:
    """Descubre y devuelve instancias de todos los sub-agentes en la carpeta sub_agents/.
    Funciona tanto en el arranque inicial como durante hot-reload sin reiniciar."""
    sub_agents = []
    pkg_name = "agent_core.sub_agents"
    try:
        # Asegurarse que el paquete está en sys.modules para imports relativos
        if pkg_name not in sys.modules:
            package = importlib.import_module(pkg_name)
        else:
            package = sys.modules[pkg_name]
        
        sub_agents_dir = os.path.join(os.path.dirname(__file__), "sub_agents")
        
        for fname in sorted(os.listdir(sub_agents_dir)):
            if fname in ("__init__.py", "base.py", "__pycache__", ".DS_Store"):
                continue
                
            item_path = os.path.join(sub_agents_dir, fname)
            
            # Formato A: archivo suelto en sub_agents/agent_name_agent.py
            if os.path.isfile(item_path) and fname.endswith(".py"):
                mod_name = fname[:-3]
                full_mod_name = f"{pkg_name}.{mod_name}"
            # Formato B: carpeta agent_name/agent_name_agent.py
            elif os.path.isdir(item_path):
                expected_file = f"{fname}_agent.py"
                if os.path.isfile(os.path.join(item_path, expected_file)):
                    mod_name = f"{fname}.{fname}_agent"
                    full_mod_name = f"{pkg_name}.{mod_name}"
                else: continue
            else: continue
                
            try:
                # Si ya está en sys.modules recuperarlo, si no importarlo
                if full_mod_name in sys.modules:
                    module = sys.modules[full_mod_name]
                else:
                    module = importlib.import_module(full_mod_name)
                    
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseSubAgent) and obj is not BaseSubAgent:
                        sub_agents.append(obj())
                        break
            except Exception as e:
                print(f"  [Discovery] Error cargando {fname}: {e}")
    except Exception as e:
        print(f"Error descubriendo agentes: {e}")
    return sub_agents

def get_dynamic_route_model(sub_agents: List[BaseSubAgent], all_tools: list = None):
    """Crea dinámicamente la clase Pydantic de enrutamiento basada en agentes descubiertos."""
    if all_tools is None:
        all_tools = []
        
    # Las opciones posibles son los nombres de los agentes descubiertos + "FINISH"
    options = [a.name for a in sub_agents] + ["FINISH"]
    
    # Construimos la descripción detallada uniendo las de cada sub-agente
    desc = "El agente encargado. "
    for a in sub_agents:
        try:
            agent_tools = [getattr(t, "name", getattr(t, "__name__", str(t))) for t in a.get_tools(all_tools)]
            tools_str = f" [herramientas: {', '.join(agent_tools)}]" if agent_tools else ""
        except Exception:
            tools_str = ""
        desc += f"'{a.name}' ({a.description}{tools_str}), "
    desc += "'FINISH' si la tarea está lista."

    # Creamos un tipo literal dinámicamente. 
    # Literal no puede ser generado con una lista en runtime de forma limpia antes de Python 3.11,
    # así que usamos un wrapper o Enum internamente, o simplemente usamos un string validador.
    # Para simplicidad y compatibilidad con pydantic v2:
    return create_model(
        'Route',
        next_node=(str, Field(description=desc)),
        instruccion=(str, Field(default="", description="Si delegas a un agente, escribe aquí una instrucción clara y directa de lo que esperas que haga. Él leerá este mensaje.")),
        respuesta_conversacional=(str, Field(default="", description="Si el next_node es FINISH, usa este campo para darle tu respuesta final en texto al usuario (ej. saludar, dar la hora, o confirmar)."))
    )

def _sanitize_messages_for_gemini(messages):
    """Sanitiza y RECORTA el contenido de los mensajes para evitar explosiones de tokens.
    
    1. Asegura secuencias válidas para Gemini (AIMessage -> ToolMessage).
    2. Recorta mensajes individuales que excedan MAX_MESSAGE_CHARS para proteger el contexto.
    """
    if not messages:
        return messages
    
    sanitized = []
    for m in messages:
        # --- Lógica de Recorte (Memory Optimization) ---
        content = getattr(m, "content", "")
        if isinstance(content, str) and len(content) > MAX_MESSAGE_CHARS:
            truncated_content = content[:MAX_MESSAGE_CHARS] + f"\n\n[... CONTENIDO RECORTADO ({len(content)} chars) para optimizar memoria ...]"
            # Creamos una copia del mensaje con el contenido recortado
            if isinstance(m, ToolMessage):
                m = ToolMessage(content=truncated_content, tool_call_id=m.tool_call_id, name=m.name)
            elif isinstance(m, AIMessage):
                m = AIMessage(content=truncated_content, tool_calls=m.tool_calls, usage_metadata=m.usage_metadata)
            elif isinstance(m, HumanMessage):
                m = HumanMessage(content=truncated_content, name=m.name)
        
        sanitized.append(m)
    
    # --- Lógica de Secuencia (Validación Gemini) ---
    # 1. Remover ToolMessages huérfanos al inicio
    while sanitized and isinstance(sanitized[0], ToolMessage):
        sanitized.pop(0)
    
    # 2. Asegurar que no empiece con un AIMessage (Gemini requiere Human/Tool/System primero)
    if not sanitized or isinstance(sanitized[0], AIMessage):
        sanitized.insert(0, HumanMessage(content="Continúa con la tarea pendiente usando tu contexto y herramientas.", name="WorkerContext"))
    
    return sanitized

def make_supervisor_node(llm, sub_agents: List[BaseSubAgent], all_tools: list):
    RouteModel = get_dynamic_route_model(sub_agents, all_tools)
    
    # Usar modelo más liviano para routing (el supervisor solo decide a quién derivar)
    import os
    supervisor_model_name = os.environ.get("MODEL_SUPERVISOR", "gemini-2.5-flash")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        supervisor_base_llm = ChatGoogleGenerativeAI(model=supervisor_model_name, temperature=0.2)
        print(f"  [Supervisor] Usando modelo liviano para routing: {supervisor_model_name}")
    except Exception as e:
        print(f"  [Supervisor] Fallo al cargar {supervisor_model_name}, usando modelo por defecto: {e}")
        supervisor_base_llm = llm
    
    supervisor_llm = supervisor_base_llm.bind_tools([RouteModel], tool_choice="any")
    
    async def supervisor_node(state: AgentState, config: RunnableConfig):
        messages = state["messages"]

        from datetime import datetime
        import os
        from zoneinfo import ZoneInfo
        
        tz_str = os.getenv("TZ", "America/Santiago")
        current_time_iso = datetime.now(ZoneInfo(tz_str)).isoformat()
        
        episodic_context = memory_utils.load_all_episodic_context(agent_name="supervisor")
        
        # Generar las reglas del prompt dinámicamente mapeadas incluyendo sus herramientas
        agent_desc_lines = []
        for a in sub_agents:
            try:
                agent_tools = [getattr(t, "name", getattr(t, "__name__", str(t))) for t in a.get_tools(all_tools)]
                tools_str = f" [Herramientas que domina: {', '.join(agent_tools)}]" if agent_tools else ""
            except Exception:
                tools_str = ""
            agent_desc_lines.append(f"- '{a.name}': {a.description}{tools_str}")
            
        agent_rules = "\\n".join(agent_desc_lines)
        
        system_prompt = SystemMessage(content=f"""Eres el Supervisor Orquestador del 'Self-Extending Agent'.
La fecha y hora actual es {current_time_iso}.

MEMORIA EPISÓDICA RELACIONADA CON TU IDENTIDAD/PREFERENCIAS:
{episodic_context}

Tu trabajo es analizar la petición del usuario, leer SIEMPRE TODO EL HISTORIAL para revisar si alguno de tus sub-agentes acaba de completar una parte del trabajo, y DELEGAR el resto usando la herramienta 'Route'.
{agent_rules}
REGLAS ESTRICTAS PARA EVITAR BUCLES:
1. DELEGACIÓN INICIAL: Delega tareas al sub-agente correcto según sus herramientas (ej. 'assistant' para agendar/emails, 'mcp' para repositorios/datos, 'youtube' para videos).
2. VERIFICA EL ÚLTIMO MENSAJE: Si el último AIMessage de un sub-agente en el historial indica que YA ATENDIÓ la solicitud del usuario (ej. dice "Ok, agendado", "Acá está el resumen", "Te lo recordaré", etc.), o SI EN EL ÚLTIMO MENSAJE EL AGENTE TE PIDE ALGO AL USUARIO (ej. "Dime la URL", "Qué video quieres?"), entonces **DEBES RESPONDERLE AL USUARIO**, es decir, `next_node`='FINISH'. NO se lo devuelvas al agente.
3. FINISH (¡MUY IMPORTANTE!): SI LA TAREA FUE COMPLETADA por el agente previo o si el agente hizo una pregunta al usuario, DEBES usar `next_node`='FINISH' y proporcionar la respuesta completa o la pregunta al usuario en el campo `respuesta_conversacional`.
4. NUNCA DELEGUES LA MISMA TAREA 2 VECES SEGUIDAS al mismo agente. Si el agente acaba de responder en el último mensaje, DEBES usar 'FINISH' (o llamar a otro distinto si hace falta). ¡Ruta de vuelta al usuario para evitar bucles infinitos!
""")
        clean_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        # Para el Supervisor: filtrar mensajes de herramientas (ToolMessage y AIMessage con solo tool_calls)
        # El Supervisor solo necesita ver texto humano/AI para decidir el routing, no payloads JSON de tools
        lightweight_messages = []
        for m in clean_messages:
            # Saltar ToolMessages (respuestas de herramientas con JSON pesado)
            if isinstance(m, ToolMessage):
                continue
            # Saltar AIMessages que solo tienen tool_calls sin texto útil
            if hasattr(m, 'tool_calls') and m.tool_calls and not (m.content and str(m.content).strip()):
                continue
            lightweight_messages.append(m)
        
        # Truncar a los últimos N mensajes para evitar explotar tokens
        if len(lightweight_messages) > MAX_CONTEXT_MESSAGES:
            lightweight_messages = lightweight_messages[-MAX_CONTEXT_MESSAGES:]
        
        print(f">> Supervisor evaluando (historial: {len(lightweight_messages)} msjs, filtrados de {len(clean_messages)})...")
        status_bus.publish_status("🧠 Supervisor analizando la solicitud...")
        response = await supervisor_llm.ainvoke([system_prompt] + lightweight_messages)
        
        next_step = "FINISH"
        if hasattr(response, "tool_calls") and response.tool_calls:
            tc = response.tool_calls[0]
            if "next_node" in tc["args"]:
                next_step = tc["args"]["next_node"].lower()
                
            resp_conv = tc["args"].get("respuesta_conversacional", "").strip()
                
            if next_step in ("finish", "end"):
                print(f"[Supervisor] El flujo general está completo según el Supervisor. Terminando (END).")
                status_bus.publish_status("✅ Tarea completada")
                from langchain_core.messages import AIMessage
                new_msg = AIMessage(
                    content=resp_conv, 
                    usage_metadata=getattr(response, "usage_metadata", {}), 
                    response_metadata=getattr(response, "response_metadata", {})
                )
                return {"messages": [new_msg], "next_node": "END"}
                
            print(f"[Supervisor] Delegando tarea (o sub-tarea pendiente) a: {next_step}")
            status_bus.publish_status(f"🔀 Delegando al agente **{next_step}**...")
            instruccion = tc["args"].get("instruccion", "").strip()
            if instruccion:
                content = f"[Instrucción del Supervisor para {next_step}]: {instruccion}"
            else:
                content = f"[Instrucción del Supervisor para {next_step}]: Por favor, atiende la solicitud del usuario de acuerdo a tu rol usando tu contexto."
            
            from langchain_core.messages import HumanMessage
            instruction_msg = HumanMessage(content=content, name="Supervisor")
            
            # ATENCIÓN: Solo devolvemos la instrucción fingida como HumanMessage. NO devolvemos
            # el 'response' original (AIMessage con tool_calls) para evitar corromper la alternancia 
            # Human/AI de la API de Gemini (INVALID_ARGUMENT).
            return {"messages": [instruction_msg], "next_node": next_step}
            
        print("[Supervisor] Respondiendo directamente o asumiendo END sin herramienta.")
        return {"messages": [response], "next_node": "END"}

    return supervisor_node

def make_agent_node(llm, tools, system_prompt_text, agent_name: str = None, custom_model: str = None):
    # Si el agente especifica un modelo a usar, instanciamos uno nuevo conservando temperature=0
    if custom_model:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model=custom_model, temperature=0)
            print(f"  [Discovery] Agente '{agent_name}' inicializado con modelo personalizado: {custom_model}")
        except Exception as e:
            print(f"  [Discovery] Fallo al cargar modelo {custom_model} para {agent_name}. Usando default. {e}")
            
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm
        
    async def agent_node(state: AgentState, config: RunnableConfig):
        thread_id = "default_session"
        if config and "configurable" in config:
            thread_id = config["configurable"].get("thread_id", "default_session")
            
        from datetime import datetime
        import os
        from zoneinfo import ZoneInfo
        
        tz_str = os.getenv("TZ", "America/Santiago")
        current_time_iso = datetime.now(ZoneInfo(tz_str)).isoformat()
        
        episodic_context = memory_utils.load_all_episodic_context(agent_name=agent_name)
        procedural_context = memory_utils.load_procedural_documentation(agent_name=agent_name)
        
        formatted_prompt = system_prompt_text \
            .replace("{current_time_iso}", current_time_iso) \
            .replace("{thread_id}", thread_id) \
            .replace("{episodic_context}", episodic_context) \
            .replace("{procedural_context}", procedural_context if procedural_context else "Aún no tienes herramientas.")
        formatted_prompt += """\n\nATENCIÓN - REGLAS PARA SUB-AGENTES TRABAJADORES:
1. NUNCA intentes usar la herramienta 'Route'. El Supervisor se encarga del routing.
2. Si tu system prompt te indica que eres el agente FINAL para la consulta: da una respuesta completa y directa al usuario. NO escribas frases como "el siguiente agente debe...", "ahora el assistant debe...", ni nada similar. TÚ eres la respuesta.
3. Solo si la tarea requiere una habilidad que realmente NO tienes (diferente tipo de integración, otra API, etc.), entonces explica brevemente qué hiciste y qué quedaría pendiente. El Supervisor lo tomará.
4. CRÍTICO: Si intentas usar una herramienta y falla reiteradamente, NO te quedes en un bucle infinito. Detente, reporta el fallo amigablemente y termina tu turno."""
        system_msg = SystemMessage(content=formatted_prompt)
        
        messages = state["messages"]
        clean_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        # Truncar a los últimos N mensajes para evitar explotar tokens
        if len(clean_messages) > MAX_CONTEXT_MESSAGES:
            clean_messages = clean_messages[-MAX_CONTEXT_MESSAGES:]
        
        # Sanitizar: asegurar que la secuencia de mensajes sea válida para Gemini
        # (no dejar ToolMessages huérfanos ni AIMessages con tool_calls sin respuesta)
        clean_messages = _sanitize_messages_for_gemini(clean_messages)
        
        print(f">> LLM Razonando en contexto Worker (historial: {len(clean_messages)} msjs)...")
        if agent_name:
            status_bus.publish_status(f"⚙️ Agente **{agent_name}** procesando...")
        response = await llm_with_tools.ainvoke([system_msg] + clean_messages)
        # Notificar si va a llamar herramientas
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_name = tc.get("name", "herramienta") if isinstance(tc, dict) else getattr(tc, "name", "herramienta")
                status_bus.publish_status(f"🔧 Usando herramienta: **{tool_name}**")
        return {"messages": [response]}
        
    return agent_node

def supervisor_condition(state: AgentState):
    next_node = state.get("next_node", "END")
    return next_node

def create_worker_condition(tools_node_name: str):
    def condition(state: AgentState):
        last_message = state["messages"][-1]
        has_tc = hasattr(last_message, "tool_calls") and last_message.tool_calls
        print(f"  [DEBUG] Worker condition: last_msg type={last_message.type}, has_tool_calls={has_tc} → {'tools' if has_tc else 'supervisor'}")
        if has_tc:
            return tools_node_name
        return "supervisor"
    return condition


class SelfExtendingAgent:
    def __init__(self):
        # Initialize memory structure and setup
        memory_utils.init_memory_structure()
        memory_utils.check_and_run_setup_wizard()
        memory_utils.check_and_run_env_wizard()
        
        # Load MCP configuration
        self.mcp_config = memory_utils.load_mcp_config()
        self.mcp_manager = MCPClientManager(self.mcp_config)
            
        # Initialize the LLM
        try:
            self.llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2)
        except Exception as e:
             self.llm = None
             print(f"Warning: Failed to initialize Gemini LLM. Ensure GOOGLE_API_KEY is set. Error: {e}")

        # The graph and memory saver
        self.graph = None
        self.memory_saver = MemorySaver()

    async def initialize(self):
        """Asynchronously connect to MCP servers and build the graph."""
        print("=> Inicializando conexiones MCP...")
        await self.mcp_manager.connect_all()
        
        tools = await self.mcp_manager.get_all_tools()
        
        # Add fallback local tools
        tools.extend([
            crear_y_ejecutar_herramienta_local, 
            usar_herramienta_local, 
            escribir_archivo_en_proyecto,
            eliminar_archivo_en_proyecto,
            instalar_dependencia_python,
            memory_utils.administrar_memoria_episodica, 
            memory_utils.administrar_memoria_procedimental,
            buscar_en_internet, 
            crear_recordatorio_solo_texto_para_usuario,
            agendar_accion_autonoma_agente,
            listar_tareas_programadas,
            crear_rutina_texto_periodica_para_usuario,
            agendar_rutina_autonoma_agente,
            eliminar_tarea_programada,
            leer_correos_recientes,
            modificar_etiquetas_correo,
            enviar_correo,
            listar_eventos_calendario,
            responder_evento_calendario,
            crear_evento_calendario,
            leer_hoja_calculo,
            escribir_hoja_calculo,
            listar_espacios_chat,
            leer_mensajes_chat,
            enviar_mensaje_chat,
            buscar_chat_directo,
            leer_google_doc,
            buscar_archivos_drive
        ])
        
        if tools:
            print(f"=> Se configuraron {len(tools)} herramientas (MCP + Fallback locales).")
            if self.llm:
                self.llm_with_tools = self.llm.bind_tools(tools)
            else:
                self.llm_with_tools = None
        else:
            print("=> No se encontraron herramientas MCP. El LLM operará sin herramientas externas.")
            self.llm_with_tools = self.llm
            
        self._all_tools = tools  # Guardamos para hot-reload
        self._sub_agents_snapshot = self._get_sub_agents_snapshot()
        self.graph = self._build_graph(tools)

    def _get_sub_agents_snapshot(self) -> frozenset:
        """Devuelve un snapshot de (nombre, mtime) de los archivos en sub_agents/."""
        sub_agents_dir = os.path.join(os.path.dirname(__file__), "sub_agents")
        result = set()
        try:
            for fname in os.listdir(sub_agents_dir):
                if fname in ("__init__.py", "base.py", "__pycache__", ".DS_Store"):
                    continue
                item_path = os.path.join(sub_agents_dir, fname)
                
                # Formato A:
                if os.path.isfile(item_path) and fname.endswith(".py"):
                    result.add((fname, os.path.getmtime(item_path)))
                # Formato B:
                elif os.path.isdir(item_path):
                    expected_file = os.path.join(item_path, f"{fname}_agent.py")
                    if os.path.isfile(expected_file):
                        result.add((f"{fname}/{fname}_agent.py", os.path.getmtime(expected_file)))
        except Exception:
            pass
        return frozenset(result)

    def _check_and_reload_graph(self):
        """Si detecta cambios en sub_agents/, reconstruye el grafo sin reiniciar."""
        current_snapshot = self._get_sub_agents_snapshot()
        if current_snapshot != self._sub_agents_snapshot:
            self._sub_agents_snapshot = current_snapshot
            print("\\n=> 🔄 Nuevo sub-agente detectado. Reconstruyendo grafo en caliente...")
            # Eliminar del cache sólo los módulos de sub-agentes individuales
            # (NO el paquete padre 'agent_core.sub_agents' para que los imports relativos sigan funcionando)
            to_remove = [
                key for key in sys.modules 
                if key.startswith("agent_core.sub_agents.") and key != "agent_core.sub_agents.base"
            ]
            for key in to_remove:
                del sys.modules[key]
            self.graph = self._build_graph(self._all_tools)
            print("=> ✅ Grafo reconstruido exitosamente.")

    def _build_graph(self, tools: list):
        # 1. Ejecutar el Auto-Discovery de Agentes
        sub_agents = discover_sub_agents()
        
        # 1.5. Propagar herramientas dinámicamente a los agentes antes de obtener descripciones
        for agent in sub_agents:
            if hasattr(agent, "set_tools"):
                agent.set_tools(tools)
                
        agent_names = [a.name for a in sub_agents]
        print(f"=> Sub-Agentes descubiertos dinámicamente: {agent_names}")
        
        # 2. Iniciar Grafo Principal
        workflow = StateGraph(AgentState)
        
        # 3. Añadir el Supervisor (ahora instanciado y dotado con la lista de agentes)
        workflow.add_node("supervisor", make_supervisor_node(self.llm, sub_agents, tools))
        
        # 4. Inyectar dinámicamente cada Sub-Agente como nodos y enlazar
        for agent in sub_agents:
            agent_tools = agent.get_tools(tools)
            prompt_text = agent.system_prompt
            
            node_name = agent.name
            tools_node_name = f"{node_name}_tools"
            
            # Intentar obtener custom model del agente si existe y no es nulo
            agent_model = getattr(agent, "model", None)
            
            # Crear y añadir nodo inteligente
            workflow.add_node(
                node_name, 
                make_agent_node(
                    self.llm, 
                    agent_tools, 
                    prompt_text, 
                    agent_name=node_name, 
                    custom_model=agent_model
                )
            )
            
            # Crear y añadir su nodo de herramientas (solo si usa herramientas)
            if agent_tools:
                workflow.add_node(tools_node_name, ToolNode(agent_tools))
                workflow.add_conditional_edges(
                    node_name, 
                    create_worker_condition(tools_node_name),
                    {tools_node_name: tools_node_name, "supervisor": "supervisor"}
                )
                workflow.add_edge(tools_node_name, node_name)
            else:
                workflow.add_edge(node_name, "supervisor")

        # 5. Enlaces (Edges) de control
        routing_map = {n: n for n in agent_names}
        routing_map["END"] = END
        
        workflow.add_conditional_edges("supervisor", supervisor_condition, routing_map)
        workflow.add_edge(START, "supervisor")
        
        # 6. Guardar nombres para filtros dinámicos en run() y process_message()
        self._agent_names = agent_names
        self._tools_nodes = [f"{n}_tools" for n in agent_names]
        
        return workflow.compile(checkpointer=self.memory_saver)

    async def run(self, user_input: str, thread_id: str = "default_session"):
        if not self.graph:
            print("Error: El agente no ha sido inicializado. Llama a initialize() primero.")
            return

        # Hot-Reload: detectar y cargar nuevos sub-agentes sin reiniciar
        self._check_and_reload_graph()
            
        print(f"\\nUsuario: {user_input}")
        
        # Provide config for short-term memory continuity
        # recursion_limit evita bucles infinitos: máx ~6 ciclos supervisor↔worker
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
        
        # State will be appended to the thread automatically
        async for output in self.graph.astream({"messages": [HumanMessage(content=user_input)]}, config=config, stream_mode="updates"):
            for node_name, node_state in output.items():
                if "messages" in node_state:
                    latest_message = node_state["messages"][-1]
                    worker_nodes = getattr(self, "_agent_names", ["dev", "assistant", "researcher"])
                    tools_nodes = getattr(self, "_tools_nodes", ["dev_tools", "assistant_tools", "researcher_tools"])
                    if node_name in worker_nodes:
                        if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
                            for tc in latest_message.tool_calls:
                                print(f"\\n[{node_name} decide usar herramienta]: {tc['name']} -> Arg: {tc['args']}")
                        else:
                            content = latest_message.content
                            if isinstance(content, list):
                                text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                                text = "".join(text_parts).strip()
                                print(f"\\nAgent ({node_name}): {text}")
                            else:
                                print(f"\\nAgent ({node_name}): {content}")
                    elif node_name == "supervisor":
                        if not (hasattr(latest_message, "tool_calls") and latest_message.tool_calls):
                            # The supervisor is responding directly
                            content = latest_message.content
                            if isinstance(content, list):
                                text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                                text = "".join(text_parts).strip()
                                print(f"\\n[Supervisor Responde]: {text}")
                            elif content:
                                print(f"\\n[Supervisor Responde]: {content}")
                    elif node_name in tools_nodes:
                        print(f"\\n[Herramienta finalizó]: {latest_message.name}")

    async def process_message(self, user_input: str, thread_id: str = "default_session", return_usage: bool = False):
        """Process a message and return the final string response (and usage if requested)."""
        if not self.graph:
            return ("Error: El agente no ha sido inicializado.", {}) if return_usage else "Error: El agente no ha sido inicializado."

        # Hot-Reload: detectar y cargar nuevos sub-agentes sin reiniciar
        self._check_and_reload_graph()
            
        print(f"\\n[API] Recibido: {user_input}")
        # recursion_limit evita bucles infinitos: máx ~6 ciclos supervisor↔worker
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
        final_answer = ""
        usage_record = {}
        try:
            async for output in self.graph.astream({"messages": [HumanMessage(content=user_input)]}, config=config, stream_mode="updates"):
                for node_name, node_state in output.items():
                    if "messages" in node_state:
                        # En algunos casos (ej: Supervisor) el estado tiene múltiples mensajes,
                        # así que aseguramos revisar todos los mensajes para no perder el AIMessage
                        msgs_to_check = node_state["messages"] if isinstance(node_state["messages"], list) else [node_state["messages"]]
                        
                        latest_message = msgs_to_check[-1]
                        
                        # Trackear cada paso individual que tenga tokens
                        for msg in msgs_to_check:
                            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                                i_toks = msg.usage_metadata.get("input_tokens", 0)
                                o_toks = msg.usage_metadata.get("output_tokens", 0)
                                if i_toks > 0 or o_toks > 0:
                                    mod_name = "Desconocido"
                                    if hasattr(msg, "response_metadata") and msg.response_metadata:
                                        mod_name = msg.response_metadata.get("model_name", "Desconocido")
                                        
                                    try:
                                        from utils.token_tracker import log_token_usage
                                        usage_record = log_token_usage(
                                            user_input=f"[{node_name}] {user_input[:50]}...",
                                            model=mod_name,
                                            input_tokens=i_toks,
                                            output_tokens=o_toks,
                                            thread_id=thread_id
                                        )
                                    except Exception as e:
                                        print(f"[API] Error trackeando tokens de {node_name}: {e}")

                        worker_nodes = getattr(self, "_agent_names", ["dev", "assistant", "researcher"])
                        if node_name in worker_nodes:
                            if hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
                                for tc in latest_message.tool_calls:
                                    print(f"\\n[API -> {node_name} decide usar herramienta]: {tc['name']}")
                            else:
                                content = latest_message.content
                                if isinstance(content, list):
                                    text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                                    text = "".join(text_parts).strip()
                                    if text: 
                                        final_answer = text
                                else:
                                    if content:
                                        final_answer = content
                        elif node_name == "supervisor":
                            if not (hasattr(latest_message, "tool_calls") and latest_message.tool_calls):
                                content = latest_message.content
                                if isinstance(content, list):
                                    text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                                    text = "".join(text_parts).strip()
                                    if text:
                                        final_answer = final_answer if final_answer else text
                                else:
                                    text = str(content).strip() if content else ""
                                    if text:
                                        final_answer = final_answer if final_answer else text
                                        
        except Exception as e:
            import traceback
            import asyncio
            error_traceback = traceback.format_exc()
            print(f"\\n[CRITICAL FATAL] Error del Sistema. Inicializando auto-curacion...\\n{str(e)}")
            
            # Auto-reparación desactivada temporalmente: esperamos confirmación interactiva
            final_answer = (
                f"⚠️ He detectado un error técnico grave (posible bucle o fallo de herramientas). "
                f"Para que evalúe y ejecute un protocolo de auto-reparación sobre mi código, envíame textualmente el siguiente comando:\\n\\n"
                f"`@dev repara este error:`\\n```\\n{str(e)}\\n```\\n\\n*(Error más detallado se guardó en la consola del servidor)*"
            )

        if return_usage:
            return final_answer, usage_record
            
        return final_answer

    async def stream_message(self, user_input: str, thread_id: str = "default_session"):
        """
        Async generator that streams the agent response as events.
        Yields dicts with 'type': 'status' | 'token' | 'done' | 'error'
        - status: intermediate step info (supervisor routing, tool calls)
        - token: a text chunk of the final response being written
        - done: final event with full text + usage data
        - error: something went wrong
        """
        if not self.graph:
            yield {"type": "error", "content": "Agente no inicializado"}
            return

        self._check_and_reload_graph()

        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
        worker_nodes = getattr(self, "_agent_names", [])
        
        full_response = ""
        supervisor_fallback = ""   # Respuesta directa del supervisor (sin worker)
        total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "model": "varios"
        }
        last_streaming_node = None  # Nodo cuyo stream de tokens estamos emitiendo

        try:
            async for event in self.graph.astream_events(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                version="v2"
            ):
                kind = event.get("event", "")
                node_name = event.get("metadata", {}).get("langgraph_node", "")

                # ── 1. Stream de tokens del LLM ──────────────────────────────────
                if kind == "on_chat_model_stream":
                    # Solo emitir tokens de nodos worker (no supervisor, no tool nodes)
                            # No emitimos tokens de workers en tiempo real (según solicitud usuario)
                            # para que solo se vea el resultado final cuando el flujo termine.
                            # full_response += text    <- No lo sumamos para evitar duplicados en 'done'
                            pass

                # ── 2. Inicio de un nodo → publicar status ───────────────────────
                elif kind == "on_chain_start" and node_name:
                    if node_name in worker_nodes:
                        msg = f"⚙️ Agente **{node_name}** procesando..."
                        status_bus.publish_status(msg)
                        yield {"type": "status", "content": msg}
                    elif node_name == "supervisor":
                        msg = "🧠 Supervisor analizando..."
                        status_bus.publish_status(msg)
                        yield {"type": "status", "content": msg}

                # ── 3. Fin de un nodo supervisor → capturar respuesta directa ────
                elif kind == "on_chain_end" and node_name == "supervisor":
                    # Si el supervisor respondió directamente (sin delegar), capturar su texto
                    # Esto ocurre cuando el supervisor decide FINISH en el primer paso
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and "messages" in output:
                        msgs = output["messages"]
                        if msgs:
                            last_msg = msgs[-1]
                            # Solo si NO es un tool_call (routing call)
                            has_tc = hasattr(last_msg, "tool_calls") and last_msg.tool_calls
                            if not has_tc:
                                raw = last_msg.content if hasattr(last_msg, "content") else ""
                                if isinstance(raw, list):
                                    raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict) and p.get("type") == "text")
                                if raw and isinstance(raw, str):
                                    supervisor_fallback = raw.strip()

                    # Caso especial: Capturar 'respuesta_conversacional' de la herramienta 'Route'
                    from langchain_core.messages import AIMessage
                    if isinstance(output, AIMessage) and output.tool_calls:
                        for tc in output.tool_calls:
                            if tc.get("name") == "Route":
                                args = tc.get("args", {})
                                if args.get("next_node", "").lower() in ("finish", "end"):
                                    supervisor_fallback = args.get("respuesta_conversacional", "").strip()

                # ── 4. Fin del LLM call → capturar usage ────────────────────────
                elif kind == "on_chat_model_end":
                    response_obj = event.get("data", {}).get("output")
                    if response_obj and hasattr(response_obj, "usage_metadata") and response_obj.usage_metadata:
                        i_toks = response_obj.usage_metadata.get("input_tokens", 0)
                        o_toks = response_obj.usage_metadata.get("output_tokens", 0)
                        if (i_toks > 0 or o_toks > 0) and node_name:
                            mod_name = "Desconocido"
                            if hasattr(response_obj, "response_metadata"):
                                mod_name = response_obj.response_metadata.get("model_name", "Desconocido")
                            try:
                                from utils.token_tracker import log_token_usage
                                usage_record = log_token_usage(
                                    user_input=f"[{node_name}] {user_input[:50]}...",
                                    model=mod_name,
                                    input_tokens=i_toks,
                                    output_tokens=o_toks,
                                    thread_id=thread_id
                                )
                                # Acumular el total de la respuesta para el frontend
                                total_usage["input_tokens"] += usage_record.get("input_tokens", 0)
                                total_usage["output_tokens"] += usage_record.get("output_tokens", 0)
                                total_usage["cost_usd"] += usage_record.get("cost_usd", 0.0)
                                if mod_name != "Desconocido":
                                    total_usage["model"] = mod_name
                                    
                            except Exception as e:
                                print(f"[stream] Error trackeando tokens: {e}")

                    # Si el nodo tiene tool_calls, reset full_response para no mezclar
                    # el "thinking" con la respuesta final
                    if response_obj and hasattr(response_obj, "tool_calls") and response_obj.tool_calls:
                        if node_name in worker_nodes:
                            for tc in response_obj.tool_calls:
                                tool_name = tc.get("name", "herramienta") if isinstance(tc, dict) else getattr(tc, "name", "herramienta")
                                msg = f"🔧 Usando herramienta: **{tool_name}**"
                                status_bus.publish_status(msg)
                                yield {"type": "status", "content": msg}
                            # Reset: lo que se escribió no es la respuesta final
                            full_response = ""

        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"\n[stream_message CRITICAL] {e}\n{error_traceback}")
            
            # Auto-repair en background (igual que process_message)
            import asyncio as _asyncio
            repair_msg = f"@dev URGENTE FALLO DE RED: {error_traceback}"
            async def auto_repair():
                try:
                    heal_cfg = {"configurable": {"thread_id": f"repair_{thread_id}"}, "recursion_limit": 50}
                    async for _ in self.graph.astream({"messages": [HumanMessage(content=repair_msg)]}, config=heal_cfg, stream_mode="updates"):
                        pass
                except Exception:
                    pass
            _asyncio.create_task(auto_repair())
            
            yield {"type": "error", "content": "Ocurrió un error técnico. Activé auto-reparación."}
            return

        # ── Evento final con texto completo + usage ──────────────────────────────
        status_bus.publish_status("✅ Tarea completada")
        final_text = full_response.strip()
        if not final_text and supervisor_fallback:
            final_text = supervisor_fallback
            
        yield {"type": "done", "content": final_text, "usage": total_usage}

    async def cleanup(self):
        """Cleanup connections."""
        await self.mcp_manager.close()

async def async_main():
    print("Iniciando Self-Extending Agent (Fase 2)...")
    agent = SelfExtendingAgent()
    
    await agent.initialize()
    
    # Iniciar el scheduler explícitamente para modo local
    start_scheduler()
    
    print("\\nEscribe 'salir' para terminar.")
    while True:
        try:
            # using run_in_executor to avoid blocking the event loop with input()
            user_input = await asyncio.get_event_loop().run_in_executor(None, input, "\\nTú: ")
            if user_input.lower() in ["salir", "exit", "quit"]:
                break
            await agent.run(user_input)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error inesperado: {e}")
            break
            
    # Detener scheduler al salir
    stop_scheduler()
    await agent.cleanup()

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
