import sys
from math import radians, sin, cos, sqrt, atan2

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """
    Calcula la distancia en kilómetros entre dos puntos geográficos
    usando la fórmula de Haversine.
    """
    # Radio promedio de la Tierra en kilómetros
    R = 6371.0

    # Convertir coordenadas de grados a radianes
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    # Diferencia de longitudes y latitudes
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    # Aplicar la fórmula de Haversine
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distancia = R * c
    return distancia

if __name__ == "__main__":
    # Verificar que se proporcionen los 4 argumentos necesarios
    if len(sys.argv) != 5:
        print("Error: Se requieren 4 argumentos: lat1 lon1 lat2 lon2", file=sys.stderr)
        sys.exit(1)

    try:
        # Convertir los argumentos de la línea de comandos a números flotantes
        latitud1 = float(sys.argv[1])
        longitud1 = float(sys.argv[2])
        latitud2 = float(sys.argv[3])
        longitud2 = float(sys.argv[4])
    except ValueError:
        print("Error: Todos los argumentos deben ser números válidos.", file=sys.stderr)
        sys.exit(1)

    # Calcular la distancia
    distancia_km = calcular_distancia_haversine(latitud1, longitud1, latitud2, longitud2)

    # Imprimir el resultado final a stdout
    print(distancia_km)