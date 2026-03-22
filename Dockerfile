# Usamos una imagen oficial de Python ligera
FROM python:3.11-slim

# Evitamos que Python genere archivos .pyc y forzamos la salida de logs sin buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Instalamos dependencias del sistema, incluyendo Node.js (requerido para los servidores MCP como npx)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos primero las dependencias para aprovechar la caché de Docker
COPY requirements.txt .

# Instalamos las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

RUN npm install -g mcp-remote
# Copiamos el resto del código del proyecto
COPY . .

# Exponemos el puerto de FastAPI / Webhook (ajustar si usas otro)
EXPOSE 8000

# Comando por defecto al ejecutar el contenedor
# Por defecto levantará el bot de Telegram con el servidor Webhook.
# Tambien puedes sobreescribirlo en tu docker-compose para correr agent_core/main.py en otro contenedor.
CMD ["python", "agent_core/telegram_bot.py"]
