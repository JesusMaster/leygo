import sys
import ast
import os

class AgentCoreModifier(ast.NodeTransformer):
    """
    Un transformador de AST que realiza dos modificaciones específicas:
    1. Agrega 'END' a la declaración 'from langgraph.graph import ...'.
    2. Agrega un mapeo 'FINISH': END a la llamada add_conditional_edges del supervisor.
    """
    def __init__(self):
        self.import_modified = False
        self.edge_modified = False

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        # Busca la importación específica desde langgraph.graph
        if node.module == 'langgraph.graph' and not self.import_modified:
            # Verifica si END ya está en la lista de nombres importados
            if not any(alias.name == 'END' for alias in node.names):
                # Si no está, lo agrega
                node.names.append(ast.alias(name='END', asname=None))
                self.import_modified = True
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # Visita recursivamente los nodos hijos primero
        self.generic_visit(node)

        # Verifica si es una llamada al método 'add_conditional_edges'
        is_target_call = (
            isinstance(node.func, ast.Attribute) and
            node.func.attr == 'add_conditional_edges'
        )

        if not is_target_call or self.edge_modified:
            return node

        # Verifica si la llamada es para el nodo 'supervisor' (primer argumento)
        if (len(node.args) > 0 and
                isinstance(node.args[0], ast.Constant) and
                node.args[0].value == "supervisor"):

            # Encuentra el argumento de tipo diccionario que contiene los mapeos
            dict_arg = None
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    dict_arg = arg
                    break
            
            if dict_arg:
                # Verifica si la clave 'FINISH' ya existe en el diccionario
                key_exists = any(
                    isinstance(k, ast.Constant) and k.value == 'FINISH'
                    for k in dict_arg.keys
                )

                if not key_exists:
                    # Agrega el nuevo par clave-valor: 'FINISH': END
                    dict_arg.keys.append(ast.Constant(value='FINISH'))
                    dict_arg.values.append(ast.Name(id='END', ctx=ast.Load()))
                    self.edge_modified = True
        
        return node

def modify_script(file_path: str):
    """
    Lee un archivo Python, aplica las transformaciones AST y lo sobreescribe.
    """
    if not os.path.isfile(file_path):
        print(f"Error: El archivo no existe en la ruta especificada: {file_path}")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()

        # Parsea el código fuente en un Árbol de Sintaxis Abstracta (AST)
        tree = ast.parse(source_code)

        # Crea una instancia del modificador y la aplica al árbol
        modifier = AgentCoreModifier()
        modified_tree = modifier.visit(tree)

        # Asegura que los nuevos nodos tengan información de ubicación
        ast.fix_missing_locations(modified_tree)

        # Si se realizó algún cambio, escribe el código modificado de vuelta al archivo
        if modifier.import_modified or modifier.edge_modified:
            # ast.unparse requiere Python 3.9+
            modified_code = ast.unparse(modified_tree)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_code)
            
            mods = []
            if modifier.import_modified:
                mods.append("importación de 'END' agregada")
            if modifier.edge_modified:
                mods.append("mapeo 'FINISH': END agregado")
            
            print(f"Éxito: Archivo '{file_path}' modificado ({', '.join(mods)}).")
        else:
            print(f"Info: El archivo '{file_path}' ya está actualizado. No se realizaron cambios.")

    except Exception as e:
        print(f"Error: Ocurrió un error inesperado al procesar el archivo '{file_path}'. Detalle: {e}")

if __name__ == "__main__":
    # La tarea original especifica un archivo concreto.
    # Se establece la ruta directamente para cumplir con la tarea y corregir el error de ejecución,
    # ya que el entorno de ejecución no proporcionó argumentos de línea de comandos.
    target_file_path = "agent_core/main.py"
    modify_script(target_file_path)