# app/redis_service.py

import redis

# Conexión a Redis (local)
redis_client = redis.StrictRedis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True  # Esto convierte respuestas en strings directamente
)

def guardar_contexto(user_id: str, mensaje: str):
    redis_client.rpush(user_id, mensaje)

def obtener_contexto(user_id: str, limite: int = 10) -> str:
    """Obtiene los últimos N mensajes del historial del usuario
    
    Args:
        user_id: ID del usuario
        limite: Número máximo de mensajes a recuperar (por defecto: 10)
        
    Returns:
        str: Historial de mensajes unidos por saltos de línea
    """
    # Obtener los últimos 'limite' mensajes (desde el más antiguo al más reciente)
    historial = redis_client.lrange(user_id, -limite, -1)
    return "\n".join(historial)