import os
import sys
import asyncio
from typing import Annotated, TypedDict, Literal, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
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
from auto_coder import crear_y_ejecutar_herramienta_local, usar_herramienta_local, escribir_archivo_en_proyecto, eliminar_archivo_en_proyecto
from web_tools import buscar_en_internet
from scheduler_manager import crear_recordatorio_solo_texto_para_usuario, listar_tareas_programadas, start_scheduler, stop_scheduler, crear_rutina_texto_periodica_para_usuario, eliminar_tarea_programada, agendar_accion_autonoma_agente, agendar_rutina_autonoma_agente
from google_tools import leer_correos_recientes, modificar_etiquetas_correo, enviar_correo, listar_eventos_calendario, responder_evento_calendario, crear_evento_calendario, leer_hoja_calculo, escribir_hoja_calculo, listar_espacios_chat, leer_mensajes_chat, enviar_mensaje_chat, buscar_chat_directo
# Máximo de mensajes recientes a enviar al LLM para evitar inflar tokens
MAX_CONTEXT_MESSAGES = 10

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
    """Sanitiza la lista de mensajes después de truncar para mantener secuencias válidas para Gemini.
    
    Gemini requiere:
    - Un ToolMessage SIEMPRE debe ir precedido por un AIMessage con tool_calls
    - Un AIMessage con tool_calls SIEMPRE debe ir seguido por su(s) ToolMessage(s) de respuesta
    
    Si la truncación cortó en medio de una secuencia, esta función limpia los huérfanos.
    """
    if not messages:
        return messages
    
    sanitized = list(messages)
    
    # 1. Remover ToolMessages huérfanos al inicio (fueron separados de su AIMessage previo)
    while sanitized and isinstance(sanitized[0], ToolMessage):
        sanitized.pop(0)
    
    # 2. Si la lista quedó vacía, o si empieza con un AIMessage, 
    # insertamos un HumanMessage de contexto. Gemini exige que las secuencias de funciones 
    # SIEMPRE tengan un HumanMessage o ToolMessage predecesor. Si un AIMessage queda de primero, crashea.
    from langchain_core.messages import HumanMessage, AIMessage
    if not sanitized or isinstance(sanitized[0], AIMessage):
        sanitized.insert(0, HumanMessage(content="Continúa con la tarea pendiente usando tu contexto y herramientas.", name="WorkerContext"))
    
    return sanitized

def make_supervisor_node(llm, sub_agents: List[BaseSubAgent], all_tools: list):
    RouteModel = get_dynamic_route_model(sub_agents, all_tools)
    
    # Usar modelo más liviano para routing (el supervisor solo decide a quién derivar)
    import os
    supervisor_model_name = os.environ.get("MODEL_SUPERVISOR", "gemini-2.5-flash-lite")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        supervisor_base_llm = ChatGoogleGenerativeAI(model=supervisor_model_name, temperature=0)
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
REGLAS:
1. SI EL USUARIO PIDE AGENDAR, MOSTRAR O PROGRAMAR ALGO PARA EL FUTURO (ej. "en 1 min", "mañana", "recuérdame", "cada x horas"): **DEBES ENVIARLO INMEDIATAMENTE AL AGENTE 'assistant'**, ya que SOLO ÉL tiene las herramientas del Scheduler. No intentes enviar la tarea a otros agentes ni ejecutarla ahora.
2. DEBES usar la herramienta `Route` devolviendo el 'next_node' si la tarea requiere acción o **si un sub-agente completó un paso pero falta otro** (ejemplo: 'mcp' leyó un archivo, pero falta enviarlo por correo, entonces asigna 'assistant').
3. PRIORIZACIÓN (Para acciones en TIEMPO REAL): El agente MCP ('mcp') contiene integraciones (GitHub, KPIs). Dale prioridad al MCP para preguntas sobre proyectos o repositorios, SIEMPRE Y CUANDO no estén pidiendo que se programe para el futuro.
4. SI TODAS LAS TAREAS FUERON COMPLETADAS por los agentes previos, O SI SÓLO ES CHARLA (preguntas generales, la hora, saludos): DEBES usar la herramienta `Route` con `next_node`='FINISH'. Y usar el campo `respuesta_conversacional` de la herramienta para escribirle el texto al usuario.
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
        response = await supervisor_llm.ainvoke([system_prompt] + lightweight_messages)
        
        next_step = "FINISH"
        if hasattr(response, "tool_calls") and response.tool_calls:
            tc = response.tool_calls[0]
            if "next_node" in tc["args"]:
                next_step = tc["args"]["next_node"].lower()
                
            resp_conv = tc["args"].get("respuesta_conversacional", "").strip()
                
            if next_step in ("finish", "end"):
                print(f"[Supervisor] El flujo general está completo según el Supervisor. Terminando (END).")
                from langchain_core.messages import AIMessage
                new_msg = AIMessage(
                    content=resp_conv, 
                    usage_metadata=getattr(response, "usage_metadata", {}), 
                    response_metadata=getattr(response, "response_metadata", {})
                )
                return {"messages": [new_msg], "next_node": "END"}
                
            print(f"[Supervisor] Delegando tarea (o sub-tarea pendiente) a: {next_step}")
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
        
        formatted_prompt = system_prompt_text.format(
            current_time_iso=current_time_iso,
            thread_id=thread_id,
            episodic_context=episodic_context,
            procedural_context=procedural_context if procedural_context else "Aún no tienes herramientas."
        )
        formatted_prompt += "\n\nATENCIÓN: Eres un Sub-Agente Trabajador. NUNCA intentes usar la herramienta 'Route' y NO intentes delegar por tu cuenta a otros agentes. Si una tarea excede tus herramientas, simplemente HAZ TU PARTE, responde con un texto explicando qué hiciste y escribe qué le toca hacer al SIGUIENTE agente (ej. 'Ya leí el archivo, ahora el assistant debe enviarlo'). El Supervisor te leerá y hará la derivación automáticamente. \nCRÍTICO: Si intentas usar una herramienta y falla reiteradamente o te devuelve error, NO te quedes pegado en un bucle infinito reintentando. Detente de inmediato, reporta el fallo y el motivo de forma amigable al usuario en texto plano, y termina tu turno."
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
        response = await llm_with_tools.ainvoke([system_msg] + clean_messages)
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
            self.llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0)
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
            buscar_chat_directo
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
        config = {"configurable": {"thread_id": thread_id}}
        
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
        config = {"configurable": {"thread_id": thread_id}}
        final_answer = ""
        usage_record = {}
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
                                    final_answer = text
                            else:
                                if content:
                                    final_answer = content

        if return_usage:
            return final_answer, usage_record
            
        return final_answer

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
