# app/redis_service.py

import redis

# Conexión a Redis (local)
redis_client = redis.StrictRedis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True  # ✅ Esto convierte respuestas en strings directamente
)

def guardar_contexto(user_id: str, mensaje: str):
    redis_client.rpush(user_id, mensaje)

def obtener_contexto(user_id: str, limite: int = 2) -> str:
    """Obtiene los últimos N mensajes del historial del usuario"""
    historial = redis_client.lrange(user_id, -limite, -1)
    return "\n".join(historial)