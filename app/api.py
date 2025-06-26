# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import logging
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar servicios
from .openai_service import get_response_from_openai
from .redis_service import guardar_contexto, obtener_contexto

# Crear el router
router = APIRouter(
    prefix="",
    tags=["chat"],
    responses={404: {"description": "No encontrado"}},
)

# Esquema de la solicitud
class MessageRequest(BaseModel):
    """Esquema para la solicitud de mensaje al chatbot"""
    user_id: str = Field(..., description="ID único del usuario")
    message: str = Field(..., min_length=1, max_length=2000, description="Mensaje del usuario")

# Esquema de la respuesta
class MessageResponse(BaseModel):
    """Esquema para la respuesta del chatbot"""
    response: str = Field(..., description="Respuesta del chatbot")

# Endpoint principal
@router.post(
    "/responder",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener respuesta del chatbot",
    description="Envía un mensaje al chatbot y recibe una respuesta generada por IA"
)
async def responder(mensaje: MessageRequest):
    """
    Procesa el mensaje del usuario, recupera el historial reciente desde Redis,
    y devuelve una respuesta generada por el modelo de IA.
    """
    try:
        logger.info(f"Mensaje de {mensaje.user_id}: {mensaje.message[:50]}..." if len(mensaje.message) > 50 else f"Mensaje de {mensaje.user_id}: {mensaje.message}")

        # Obtener historial reciente (últimos 10 mensajes)
        historial = obtener_contexto(mensaje.user_id, limite=10)

        # Armar el prompt para la IA
        if historial:
            prompt = f"Este es el historial reciente del usuario:\n{historial}\n\nUsuario dice ahora: {mensaje.message}"
        else:
            prompt = mensaje.message

        # Obtener respuesta del modelo IA
        respuesta = get_response_from_openai(
            texto=prompt,
            temperature=0.7
        )

        # Guardar el nuevo mensaje como parte del contexto
        guardar_contexto(mensaje.user_id, mensaje.message)

        logger.info(f"Respuesta generada: {respuesta[:150]}..." if len(respuesta) > 150 else f"Respuesta generada: {respuesta}")

        return MessageResponse(response=respuesta)

    except Exception as e:
        error_msg = f"Error al procesar la solicitud: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "Error interno del servidor",
                "message": str(e)
            }
        )
