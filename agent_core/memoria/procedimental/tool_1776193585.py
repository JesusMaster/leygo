import sys
import os
import re

def modificar_agente(file_path: str):
    """
    Asegura que el import de END y el mapeo 'FINISH': END en el nodo supervisor existan en el archivo.

    Args:
        file_path (str): La ruta al archivo a modificar.
    """
    if not os.path.exists(file_path):
        print(f"Error: El archivo '{file_path}' no fue encontrado.")
        sys.exit(1)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error al leer el archivo '{file_path}': {e}")
        sys.exit(1)

    original_content = "".join(lines)
    modified_content = original_content

    # --- Tarea 1: Asegurar la presencia de 'from langgraph.graph import END' ---
    import_line_to_add = 'from langgraph.graph import END'
    if import_line_to_add not in modified_content:
        # Intentar agregar después del último import de langgraph
        modified_content = re.sub(
            r'(from langgraph\..*?\n)',
            f'\\1{import_line_to_add}\n',
            modified_content,
            count=1
        )
        # Si no se encontró ningún import de langgraph, buscar cualquier import
        if import_line_to_add not in modified_content:
             modified_content = re.sub(
                r'(import .*?\n|from .*?\n)',
                f'\\1{import_line_to_add}\n',
                modified_content,
                count=1
            )
        # Si aún no hay imports, agregarlo al principio
        if import_line_to_add not in modified_content:
            modified_content = f"{import_line_to_add}\n" + modified_content


    # --- Tarea 2: Agregar el mapeo 'FINISH': END si es necesario ---
    # Usamos una expresión regular más robusta que maneja múltiples líneas
    # y diferentes tipos de comillas.
    pattern = re.compile(
        r"(graph\.add_conditional_edges\(\s*['\"]supervisor['\"],\s*.*?\{)",
        re.DOTALL
    )
    
    match = pattern.search(modified_content)
    
    if match:
        start_pos = match.end(1)
        # Buscar el diccionario completo para no modificar otras partes del código
        open_braces = 1
        end_pos = -1
        for i, char in enumerate(modified_content[start_pos:]):
            if char == '{':
                open_braces += 1
            elif char == '}':
                open_braces -= 1
                if open_braces == 0:
                    end_pos = start_pos + i
                    break
        
        if end_pos != -1:
            dict_content = modified_content[start_pos:end_pos]
            # Verificar si 'FINISH' o "FINISH" ya existe en el diccionario
            if not re.search(r"['\"]FINISH['\"]\s*:", dict_content):
                # Encontrar la última llave o coma para insertar antes
                last_char_match = re.search(r",\s*$", dict_content.rstrip())
                if last_char_match:
                    # Si termina en coma, simplemente agregamos la nueva línea
                    insertion_point = start_pos + last_char_match.start()
                    line_to_get_indent = modified_content[:insertion_point].split('\n')[-1]
                    indentation = ' ' * (len(line_to_get_indent) - len(line_to_get_indent.lstrip(' ')))
                    new_mapping = f",\n{indentation}'FINISH': END"
                    modified_content = modified_content[:insertion_point] + new_mapping + modified_content[insertion_point:]
                else:
                    # Si no termina en coma, la agregamos al elemento anterior y luego la nueva línea
                    # Esto es más complejo, una solución más simple es insertar antes del '}'
                    line_to_get_indent = modified_content[:end_pos].split('\n')[-1]
                    indentation = ' ' * (len(line_to_get_indent) - len(line_to_get_indent.lstrip(' ')))
                    # Asegurarse de que la línea anterior tenga una coma
                    content_before = modified_content[:end_pos].rstrip()
                    if content_before.endswith(','):
                         new_mapping = f"\n{indentation}'FINISH': END\n"
                    else:
                         new_mapping = f",\n{indentation}'FINISH': END\n"
                    
                    modified_content = content_before + new_mapping + modified_content[end_pos:]


    # --- Tarea 3: Sobrescribir el archivo si hubo cambios ---
    if modified_content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            print(f"Archivo '{file_path}' modificado exitosamente.")
        except Exception as e:
            print(f"Error al escribir en el archivo '{file_path}': {e}")
            sys.exit(1)
    else:
        print(f"El archivo '{file_path}' ya está configurado correctamente. No se realizaron cambios.")


if __name__ == "__main__":
    # El error indica que el script fue llamado sin argumentos.
    # Para corregir esto y hacerlo más robusto para el agente que lo llama,
    # se asume una ruta por defecto si no se proporciona ninguna.
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        # La tarea original menciona 'agent_core/main.py', así que se usa como valor por defecto.
        target_file = 'agent_core/main.py'
    
    modificar_agente(target_file)