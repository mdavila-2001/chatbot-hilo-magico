# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
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

from .openai_service import get_response_from_openai

router = APIRouter(
    prefix="",
    tags=["chat"],
    responses={404: {"description": "No encontrado"}},
)

class MessageRequest(BaseModel):
    """Esquema para la solicitud de mensaje al chatbot"""
    message: str = Field(..., min_length=1, max_length=2000, description="Mensaje del usuario")

class MessageResponse(BaseModel):
    """Esquema para la respuesta del chatbot"""
    response: str = Field(..., description="Respuesta del chatbot")

@router.post(
    "/responder",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener respuesta del chatbot",
    description="Envía un mensaje al chatbot y recibe una respuesta generada por IA"
)
async def responder(mensaje: MessageRequest):
    """
    Endpoint principal para interactuar con el chatbot.
    
    Procesa el mensaje del usuario y devuelve una respuesta generada por el modelo de IA.
    """
    try:
        logger.info(f"Mensaje recibido: {mensaje.message[:50]}..." if len(mensaje.message) > 50 else f"Mensaje recibido: {mensaje.message}")
        
        # Obtener respuesta del servicio de OpenAI
        respuesta = get_response_from_openai(
            texto=mensaje.message,
            temperature=0.7  # Valor por defecto
        )
        
        logger.info(f"Respuesta generada: {respuesta[:150]}..." if len(respuesta) > 150 else f"Respuesta generada: {respuesta}")
        
        return MessageResponse(
            response=respuesta
        )
        
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