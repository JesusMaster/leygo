import os
import subprocess
import time
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from e2b_code_interpreter import Sandbox

import memory_utils

@tool
def crear_y_ejecutar_herramienta_local(descripcion_tarea: str, argumentos_de_prueba: str = "") -> str:
    """
    Usa esta herramienta como último recurso (fallback) cuando el usuario pida hacer algo 
    para lo cual no tienes una herramienta MCP disponible.
    Generará código Python para resolver la tarea, lo guardará en memoria y lo ejecutará.
    Args:
        descripcion_tarea: Una descripción genérica de la herramienta a crear.
        argumentos_de_prueba: Texto con los argumentos a usar en la validación (ej. "España").
    """
    print(f"\\n[AutoCoder] Intentando crear herramienta para: {descripcion_tarea} con test-args: '{argumentos_de_prueba}'")
    
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)
    except Exception as e:
        return f"Error iniciando AutoCoder LLM: {e}"

    prompt = f"""
    Eres un programador Python experto construyendo sub-herramientas modulares. 
    Escribe un script de Python 3 que cumpla EXACTAMENTE con esta tarea:
    {descripcion_tarea}
    
    Reglas estrictas e inquebrantables:
    1. El código debe ser completamente autónomo y ejecutable por sí solo. 
    2. Imprime sólo el resultado o la salida final hacia `stdout` usando `print()`. El agente principal leerá lo que imprimas.
    3. Trata de usar sólo librerías estándar de Python (os, sys, json, urllib, etc.) si es posible.
    4. NO envuelvas el código en bloques markdown (```python ... ```).
    5. OBLIGATORIO: TODO SCRIPT DEBE ESTAR PARAMETRIZADO mediante `sys.argv` (comenzando localmente en sys.argv[1]). NUNCA hardcodees información. Si te piden un script para buscar la hora en "Londres", tú escribirás un script genérico al que se le deba pasar la ciudad por parámetro.
    6. PROHIBIDO mezclar dominios: si se te piden 2 cosas sin relación (ej. buscar hora y buscar clima), haz SOLAMENTE EL CÓDIGO PARA LA PRIMERA. Escribe herramientas genéricas, modulares y atómicas.
    """
    
    # Retry loop simulating a basic test-driven sandbox
    max_retries = 3
    codigo_python = ""
    error_output = ""
    
    task_name = f"tool_{int(time.time())}"
    py_filename = f"{task_name}.py"
    md_filename = f"{task_name}.md"
    
    for intento in range(max_retries):
        if intento > 0:
            print(f"[AutoCoder] Reintentando (Intento {intento+1}/{max_retries}). Corrigiendo error...")
            retry_prompt = f"""
            El código que generaste falló con este error:
            {error_output}
            
            Corrige el código. Retorna ÚNICAMENTE el código en crudo sin tags markdown.
            """
            response = llm.invoke([HumanMessage(content=retry_prompt)])
        else:
            response = llm.invoke([HumanMessage(content=prompt)])
            
        codigo_python = response.content.strip()
        
        # Super simple cleanup in case the LLM stubbornly adds markdown
        if codigo_python.startswith("```python"):
            codigo_python = codigo_python[9:]
        if codigo_python.endswith("```"):
            codigo_python = codigo_python[:-3]
        codigo_python = codigo_python.strip()

        # Save to sandbox
        sandbox_path = os.path.join(memory_utils.SANDBOX_DIR, py_filename)
        with open(sandbox_path, 'w', encoding='utf-8') as f:
            f.write(codigo_python)
            
        # Verify if E2B is available
        use_e2b = bool(os.environ.get("E2B_API_KEY"))
        
        if use_e2b:
            # Execute in remote E2B Sandbox
            print(f"[AutoCoder] Ejecutando {py_filename} en sandbox E2B...")
            try:
                with Sandbox() as sandbox:
                    codigo_a_ejecutar = codigo_python
                    if argumentos_de_prueba:
                        import shlex
                        args_list = shlex.split(argumentos_de_prueba)
                        args_str = ", ".join(f"'{a}'" for a in args_list)
                        codigo_a_ejecutar = f"import sys\\nsys.argv = ['{py_filename}', {args_str}]\\n" + codigo_python
                        
                    # E2B sandbox.run_code returns an Execution object
                    execution = sandbox.run_code(codigo_a_ejecutar, timeout=15)
                    
                    # Check for errors in execution
                    if execution.error:
                        error_msg = f"{execution.error.name}: {execution.error.value}\\n{execution.error.traceback}"
                        error_output = error_msg.strip()
                        print(f"[AutoCoder] Error en ejecución E2B: {error_output}")
                    else:
                        print(f"[AutoCoder] Ejecución exitosa de E2B.")
                        
                        # Extraer stdout
                        stdout_str = "\n".join(execution.logs.stdout)
                        
                        # Save to procedural memory on success
                        memory_utils.save_procedural_memory(py_filename, codigo_python)
                        
                        # Limpiar sandbox después de validación exitosa (E2B)
                        try:
                            if os.path.exists(sandbox_path):
                                os.remove(sandbox_path)
                                print(f"[AutoCoder] Limpieza E2B: {sandbox_path} eliminado del sandbox.")
                        except Exception as e:
                            print(f"[AutoCoder] Advertencia: No se pudo eliminar {sandbox_path}: {e}")
                            
                        # Create documentation
                        doc_prompt = f"""Escribe la documentación oficial en formato Markdown para la herramienta recién creada en el archivo `{py_filename}`.
La herramienta fue concebida bajo estas instrucciones: '{descripcion_tarea}'

Tu documentación debe seguir exactamente esta estructura de Manual de Uso:
# Habilidad: [Nombre deducido]
**Archivo:** `{py_filename}`

## Descripción
[Qué hace esta herramienta y para qué sirve]

## Requerimientos y Credenciales
[Si necesita algún Token PAT, variables como E2B_API_KEY, o paquetes especiales, lístalos. Si no, "Ninguno"]

## Parámetros Esperados (si se modifica)
[Variables o constantes usadas dentro del script]
"""
                        doc_response = llm.invoke([HumanMessage(content=doc_prompt)])
                        memory_utils.save_procedural_memory(md_filename, doc_response.content)
                        
                        return f"Éxito ejecutando herramienta auto-generada remota. Salida:\\n{stdout_str.strip()}"
                        
            except Exception as e:
                error_output = str(e)
                print(f"[AutoCoder] Error fatal al conectar/ejecutar en E2B: {error_output}")
        else:
            # Fallback to local execution
            print(f"[AutoCoder] E2B_API_KEY no encontrada. Ejecutando {py_filename} localmente (FALLBACK)...")
            try:
                import shlex
                command = ['python3', sandbox_path]
                if argumentos_de_prueba:
                    command.extend(shlex.split(argumentos_de_prueba))
                    
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0:
                    print(f"[AutoCoder] Ejecución local exitosa.")
                    memory_utils.save_procedural_memory(py_filename, codigo_python)
                    
                    # Limpiar sandbox después de validación exitosa (Local)
                    try:
                        if os.path.exists(sandbox_path):
                            os.remove(sandbox_path)
                            print(f"[AutoCoder] Limpieza Local: {sandbox_path} eliminado del sandbox.")
                    except Exception as e:
                        print(f"[AutoCoder] Advertencia: No se pudo eliminar {sandbox_path}: {e}")
                        
                    doc_prompt = f"""Escribe la documentación oficial en formato Markdown para la herramienta recién creada en el archivo `{py_filename}`.
La herramienta fue concebida bajo estas instrucciones: '{descripcion_tarea}'

Tu documentación debe seguir exactamente esta estructura de Manual de Uso:
# Habilidad: [Nombre deducido]
**Archivo:** `{py_filename}`

## Descripción
[Qué hace esta herramienta y para qué sirve]

## Requerimientos y Credenciales
[Si necesita algún Token PAT, variables como E2B_API_KEY, o paquetes especiales, lístalos. Si no, "Ninguno"]

## Parámetros Esperados (si se modifica)
[Variables o constantes usadas dentro del script]
"""
                    doc_response = llm.invoke([HumanMessage(content=doc_prompt)])
                    memory_utils.save_procedural_memory(md_filename, doc_response.content)
                    
                    return f"Éxito ejecutando herramienta auto-generada local. Salida:\\n{result.stdout.strip()}"
                else:
                    error_output = result.stderr.strip()
                    if not error_output:
                        error_output = result.stdout.strip()
                    if not error_output:
                        error_output = f"Fallo ejecución con exit-code: {result.returncode} sin logs impresos."
                    print(f"[AutoCoder] Error en ejecución local: {error_output}")
                    
            except subprocess.TimeoutExpired:
                error_output = "El script tardó más de 15 segundos y fue interrumpido (Timeout)."
                print(f"[AutoCoder] {error_output}")
            except Exception as e:
                error_output = str(e)
                print(f"[AutoCoder] Error fatal local: {error_output}")

    return f"Fallo al crear y ejecutar la herramienta tras {max_retries} intentos. Último error: {error_output}"

@tool
def usar_herramienta_local(nombre_script: str, argumentos: str = "") -> str:
    """
    Usa esta herramienta cuando exista un manual en tu CATÁLOGO DE HABILIDADES PROCEDIMENTALES 
    que resuelva la tarea solicitada. 
    Ejecuta el script de la habilidad (.py) pasando los argumentos adicionales especificados.
    Args:
        nombre_script: El nombre exacto del archivo indicado en el catálogo (ej: tool_123.py).
        argumentos: Argumentos requeridos por el script separados por espacios (opcional).
    """
    print(f"\\n[AutoCoder] Intentando reutilizar habilidad guardada: {nombre_script} con args: '{argumentos}'")
    
    script_path = os.path.join(memory_utils.PROCEDIMENTAL_DIR, nombre_script)
    if not os.path.exists(script_path):
        return f"Error: No se encontró el script {nombre_script} en la memoria procedimental."
        
    try:
        # Construct command
        command = ['python3', script_path]
        if argumentos:
            import shlex
            command.extend(shlex.split(argumentos))
            
        print(f"[AutoCoder] Ejecutando comando local: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        
        if result.returncode == 0:
            return f"Éxito ejecutando herramienta {nombre_script}. Salida:\\n{result.stdout.strip()}"
        else:
            return f"Error ejecutando herramienta {nombre_script}: {result.stderr.strip()}"
            
    except subprocess.TimeoutExpired:
        return f"La ejecución de {nombre_script} tardó más de 15 segundos y fue interrumpida."
    except Exception as e:
        return f"Error fatal al intentar usar {nombre_script}: {str(e)}"

@tool
def escribir_archivo_en_proyecto(ruta_relativa: str, contenido: str) -> str:
    """
    Escribe (o sobreescribe) un archivo de texto/código en el proyecto, dado una ruta 
    relativa desde la raíz del proyecto (ej. 'agent_core/sub_agents/fitness_agent.py').
    Usa esta herramienta para crear nuevos sub-agentes, scripts, o cualquier archivo
    que deba persistir en el sistema de archivos del proyecto.
    Args:
        ruta_relativa: Ruta relativa desde la raíz del proyecto (ej. 'agent_core/sub_agents/fitness_agent.py').
        contenido: Contenido completo del archivo a escribir.
    """
    try:
        # Calculamos la raíz del proyecto (2 niveles arriba de este archivo en agent_core/)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(project_root, ruta_relativa)
        
        # Creamos los directorios intermedios si no existen
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(contenido)
        
        print(f"[AutoCoder] Archivo escrito exitosamente en: {full_path}")
        return f"✅ Archivo '{ruta_relativa}' creado/actualizado correctamente en el proyecto."
    except Exception as e:
        return f"❌ Error al escribir el archivo '{ruta_relativa}': {str(e)}"

@tool
def eliminar_archivo_en_proyecto(ruta_relativa: str) -> str:
    """
    Elimina un archivo del proyecto, dado una ruta relativa desde la raíz 
    (ej. 'agent_core/sub_agents/fitness_agent.py').
    Úsalo cuando el usuario pida eliminar, destruir o borrar un sub-agente,
    script o archivo generado previamente.
    Args:
        ruta_relativa: Ruta relativa del archivo a eliminar.
    """
    try:
        import shutil
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(project_root, ruta_relativa)
        
        if not os.path.exists(full_path):
            return f"❌ El archivo o directorio '{ruta_relativa}' no existe."
            
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
            print(f"[AutoCoder] Directorio eliminado exitosamente: {full_path}")
            return f"🗑️ Directorio '{ruta_relativa}' y su contenido eliminados del proyecto con éxito."
        else:
            os.remove(full_path)
            print(f"[AutoCoder] Archivo eliminado exitosamente: {full_path}")
            return f"🗑️ Archivo '{ruta_relativa}' eliminado del proyecto con éxito."
    except Exception as e:
        return f"❌ Error al eliminar '{ruta_relativa}': {str(e)}"

