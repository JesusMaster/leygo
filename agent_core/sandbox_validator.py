import os
import uuid
import docker
import tarfile
import io
import ast

def _ast_security_check(file_path: str) -> tuple[bool, str]:
    """Escanea el código fuente con AST buscando importaciones prohibidas."""
    banned_modules = {"os", "sys", "subprocess", "socket", "requests", "urllib", "pty", "shutil", "builtins"}
    
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
        
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"Error de sintaxis detectado antes del sandbox: {e}"
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base_module = alias.name.split('.')[0]
                if base_module in banned_modules:
                    return False, f"AST Security Block: Importación de módulo prohibido '{alias.name}'. Los agentes generados no tienen acceso a librerías de sistema/red."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base_module = node.module.split('.')[0]
                if base_module in banned_modules:
                    return False, f"AST Security Block: Importación de módulo prohibido '{node.module}'. Los agentes generados no tienen acceso a librerías de sistema/red."
                    
    return True, "AST Check Pasado"

def _create_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        print(f"[Sandbox] No se pudo conectar a Docker: {e}")
        return None

def validate_code_in_sandbox(file_path: str, is_sub_agent: bool = False) -> tuple[bool, str]:
    """
    Ejecuta el script en un contenedor Docker efímero con red deshabilitada y sistema de archivos host de solo lectura.
    Valida que el archivo no contenga errores de sintaxis y que su importación sea segura (no rompa el entorno ni intente exfiltrar datos).
    """
    # 1. Validación AST Estática
    ast_ok, ast_msg = _ast_security_check(file_path)
    if not ast_ok:
        return False, ast_msg

    # 2. Validación Dinámica (Docker Sandbox)
    client = _create_docker_client()
    if not client:
        # Si no hay Docker (ej: servidor sin socket), podemos decidir bloquear o permitir.
        # Por seguridad extrema B2B, podríamos bloquear, pero para no romper a los devs sin docker:
        return False, "Docker no está disponible para Sandboxing. Operación rechazada por políticas de seguridad."

    # Preparar rutas
    abs_file_path = os.path.abspath(file_path)
    file_name = os.path.basename(abs_file_path)
    
    # Asumimos que agent_core está en el directorio padre de este script
    agent_core_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Vamos a usar la imagen python:3.11-slim (que ya está cacheada localmente)
    image_name = "python:3.11-slim"
    
    try:
        # Pull the image if it doesn't exist
        try:
            client.images.get(image_name)
        except docker.errors.ImageNotFound:
            client.images.pull(image_name)

        # Generar un comando de prueba
        if is_sub_agent:
            # Para sub-agentes, necesitamos simular la importación como lo haría el Orquestador
            # Le quitamos la extensión .py
            module_name = file_name[:-3] if file_name.endswith('.py') else file_name
            # Lo importaremos asumiendo que está en agent_core.sub_agents
            test_cmd = f"python -c \\\"import agent_core.sub_agents.{module_name}\\\""
        else:
            # Para scripts normales o herramientas
            test_cmd = f"python -m py_compile /app/sandbox_test/{file_name} && python /app/sandbox_test/{file_name}"

        # Configurar los volumenes:
        # - agent_core -> /app/agent_core (Read-Only)
        # - el archivo a probar -> /app/agent_core/sub_agents/archivo.py (Read-Only) si es agente
        # o -> /app/sandbox_test/archivo.py si es genérico
        
        volumes = {
            agent_core_dir: {'bind': '/app/agent_core', 'mode': 'ro'}
        }
        
        if is_sub_agent:
            volumes[abs_file_path] = {'bind': f'/app/agent_core/sub_agents/{file_name}', 'mode': 'ro'}
        else:
            volumes[abs_file_path] = {'bind': f'/app/sandbox_test/{file_name}', 'mode': 'ro'}

        # Correr el contenedor
        print(f"[Sandbox] Lanzando contenedor efímero para validar: {file_name}...")
        container = client.containers.run(
            image=image_name,
            command=["sh", "-c", test_cmd],
            volumes=volumes,
            working_dir="/app",
            network_mode="none",  # BLOQUEO TOTAL DE RED
            mem_limit="128m",     # Límite estricto de memoria
            cpu_quota=50000,      # Límite del 50% de CPU
            remove=True,          # Auto-destrucción al terminar
            detach=True,
            environment={"PYTHONPATH": "/app"}
        )
        
        # Esperar hasta 10 segundos
        result = container.wait(timeout=10)
        logs = container.logs().decode('utf-8')
        
        if result['StatusCode'] == 0:
            print(f"[Sandbox] Validación exitosa para {file_name}.")
            return True, "Validación en Sandbox aprobada."
        else:
            print(f"[Sandbox] Rechazado. Código de salida: {result['StatusCode']}\\nLogs:\\n{logs}")
            return False, f"El código falló la validación en el Sandbox (Exit {result['StatusCode']}). Posible error de sintaxis, importación o intento de acción bloqueada.\\nSalida:\\n{logs}"
            
    except docker.errors.ContainerError as e:
         return False, f"Error del contenedor en Sandbox: {e}"
    except docker.errors.APIError as e:
         return False, f"Error de API Docker: {e}"
    except Exception as e:
         return False, f"Timeout o error en Sandbox: {e}"
