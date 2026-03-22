"""
status_bus.py
=============
Bus de estado global para emitir eventos de progreso del agente en tiempo real.
Los consumers (SSE endpoint) se suscriben y reciben actualizaciones live.
"""
import asyncio
from typing import Set

# Conjunto de colas activas (una por cliente SSE conectado)
_subscribers: Set[asyncio.Queue] = set()

def subscribe() -> asyncio.Queue:
    """Registra un nuevo consumidor SSE. Devuelve su cola privada."""
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.add(q)
    return q

def unsubscribe(q: asyncio.Queue):
    """Elimina un consumidor SSE al desconectarse."""
    _subscribers.discard(q)

def publish_status(message: str):
    """
    Publica un mensaje de estado a todos los consumidores SSE conectados.
    Se puede llamar desde código síncrono o asíncrono.
    Los mensajes no entregables (cola llena) se descartan silenciosamente.
    """
    to_remove = set()
    for q in list(_subscribers):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            pass  # Cliente lento — se pierde el mensaje, no es crítico
        except Exception:
            to_remove.add(q)
    _subscribers.difference_update(to_remove)
