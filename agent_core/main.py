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
from scheduler_manager import programar_recordatorio, listar_recordatorios, start_scheduler, stop_scheduler, programar_intervalo_dinamico, eliminar_recordatorio
from google_tools import leer_correos_recientes, modificar_etiquetas_correo, enviar_correo, listar_eventos_calendario, responder_evento_calendario, crear_evento_calendario, leer_hoja_calculo, escribir_hoja_calculo, listar_espacios_chat, leer_mensajes_chat, enviar_mensaje_chat, buscar_chat_directo

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

def get_dynamic_route_model(sub_agents: List[BaseSubAgent]):
    """Crea dinámicamente la clase Pydantic de enrutamiento basada en agentes descubiertos."""
    # Las opciones posibles son los nombres de los agentes descubiertos + "FINISH"
    options = [a.name for a in sub_agents] + ["FINISH"]
    
    # Construimos la descripción detallada uniendo las de cada sub-agente
    desc = "El agente encargado. "
    for a in sub_agents:
        desc += f"'{a.name}' ({a.description}), "
    desc += "'FINISH' si la tarea está lista."

    # Creamos un tipo literal dinámicamente. 
    # Literal no puede ser generado con una lista en runtime de forma limpia antes de Python 3.11,
    # así que usamos un wrapper o Enum internamente, o simplemente usamos un string validador.
    # Para simplicidad y compatibilidad con pydantic v2:
    return create_model(
        'Route',
        next_node=(str, Field(description=desc)) # TODO: Aquí GEMINI se restringe por el str normal. Confiaremos en la docstring.
    )

def make_supervisor_node(llm, sub_agents: List[BaseSubAgent]):
    RouteModel = get_dynamic_route_model(sub_agents)
    supervisor_llm = llm.bind_tools([RouteModel])
    
    async def supervisor_node(state: AgentState, config: RunnableConfig):
        messages = state["messages"]
        if len(messages) > 0 and isinstance(messages[-1], (BaseMessage)) and messages[-1].type == "ai":
            # Solo terminar si el worker YA respondió sin tool_calls pendientes
            has_tool_calls = hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls
            if not has_tool_calls:
                print(f"[Supervisor] Trabajo del sub-agente '{messages[-1].name if hasattr(messages[-1], 'name') else 'worker'}' concluido (END).")
                # Passthrough the worker's final answer instead of re-evaluating
                return {"next_node": "END"}

        import datetime
        current_time_iso = datetime.datetime.now().astimezone().isoformat()
        
        # Generar las reglas del prompt dinámicamente mapeadas
        agent_rules = "\\n".join([f"- '{a.name}': {a.description}" for a in sub_agents])
        
        system_prompt = SystemMessage(content=f"""Eres el Supervisor Orquestador del 'Self-Extending Agent'.
La fecha y hora actual es {current_time_iso}.
Tu trabajo es analizar la petición del usuario y DELEGAR usando la herramienta 'Route'.
{agent_rules}

REGLAS:
1. DEBES usar la herramienta `Route` devolviendo el 'next_node' si la tarea requiere acción.
2. Si es un saludo genérico o plática, responde amigablemente y NO uses la herramienta `Route` (terminará en FINISH).
3. PRIORIZACIÓN: El agente MCP ('mcp') contiene las integraciones clave de la empresa (GitHub, KPIs, Documentación interna, APIs). SIEMPRE dale prioridad al MCP para preguntas sobre proyectos, repositorios o negocio. Usa el 'researcher' SÓLO como ÚLTIMO RECURSO para búsquedas generales de la web pública (noticias, eventos).
""")
        clean_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        print(f">> Supervisor evaluando (historial: {len(clean_messages)} msjs)...")
        response = await supervisor_llm.ainvoke([system_prompt] + clean_messages)
        
        next_step = "FINISH"
        if hasattr(response, "tool_calls") and response.tool_calls:
            tc = response.tool_calls[0]
            if "next_node" in tc["args"]:
                next_step = tc["args"]["next_node"].lower()
                
            print(f"[Supervisor] Delegando tarea a: {next_step}")
            tool_msg = ToolMessage(content=f"Delegado a {next_step}", tool_call_id=tc["id"])
            return {"messages": [response, tool_msg], "next_node": next_step}
            
        print("[Supervisor] Respondiendo directamente (END).")
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
            
        import datetime
        current_time_iso = datetime.datetime.now().astimezone().isoformat()
        episodic_context = memory_utils.load_all_episodic_context(agent_name=agent_name)
        procedural_context = memory_utils.load_procedural_documentation(agent_name=agent_name)
        
        formatted_prompt = system_prompt_text.format(
            current_time_iso=current_time_iso,
            thread_id=thread_id,
            episodic_context=episodic_context,
            procedural_context=procedural_context if procedural_context else "Aún no tienes herramientas."
        )
        system_msg = SystemMessage(content=formatted_prompt)
        
        messages = state["messages"]
        clean_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        print(f">> LLM Razonando en contexto Worker...")
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
            programar_recordatorio,
            listar_recordatorios,
            programar_intervalo_dinamico,
            eliminar_recordatorio,
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
        workflow.add_node("supervisor", make_supervisor_node(self.llm, sub_agents))
        
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

    async def process_message(self, user_input: str, thread_id: str = "default_session") -> str:
        """Process a message and return the final string response directly (useful for APIs)."""
        if not self.graph:
            return "Error: El agente no ha sido inicializado."

        # Hot-Reload: detectar y cargar nuevos sub-agentes sin reiniciar
        self._check_and_reload_graph()
            
        print(f"\\n[API] Recibido: {user_input}")
        config = {"configurable": {"thread_id": thread_id}}
        final_answer = ""
        
        async for output in self.graph.astream({"messages": [HumanMessage(content=user_input)]}, config=config, stream_mode="updates"):
            for node_name, node_state in output.items():
                if "messages" in node_state:
                    latest_message = node_state["messages"][-1]
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
