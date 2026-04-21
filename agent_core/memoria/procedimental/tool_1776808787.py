import sys
import os
import shutil

def eliminar_directorio_recursivo(ruta_directorio):
    """
    Elimina un directorio y todo su contenido de forma recursiva.

    Args:
        ruta_directorio (str): La ruta al directorio que se va a eliminar.
    """
    try:
        # Comprobar si la ruta existe y es un directorio
        if not os.path.isdir(ruta_directorio):
            print(f"Error: La ruta '{ruta_directorio}' no existe o no es un directorio.", file=sys.stderr)
            return

        # Eliminar el árbol de directorios
        shutil.rmtree(ruta_directorio)
        print(f"Directorio '{ruta_directorio}' y todo su contenido han sido eliminados exitosamente.")

    except PermissionError:
        print(f"Error: Permiso denegado para eliminar '{ruta_directorio}'.", file=sys.stderr)
    except OSError as e:
        print(f"Error al eliminar el directorio '{ruta_directorio}': {e}", file=sys.stderr)
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python <nombre_script>.py <ruta_directorio>", file=sys.stderr)
        sys.exit(1)

    ruta_a_eliminar = sys.argv[1]
    eliminar_directorio_recursivo(ruta_a_eliminar)