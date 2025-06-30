from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import logging
from app.openai_service import get_response_from_openai
from app.redis_service import guardar_contexto, obtener_contexto

router = APIRouter(tags=["Chat"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageRequest(BaseModel):
    user_id: str = Field(..., description="ID del usuario")
    message: str = Field(..., description="Mensaje enviado por el usuario")

class MessageResponse(BaseModel):
    response: str

@router.post("/v1/responder", response_model=MessageResponse)
async def responder(mensaje: MessageRequest):
    try:
        logger.info(f"📨 Mensaje de {mensaje.user_id}: {mensaje.message}")
        
        # Guardar el mensaje del usuario en el historial
        guardar_contexto(mensaje.user_id, f"Usuario: {mensaje.message}")
        
        # Obtener el historial de la conversación
        contexto = obtener_contexto(mensaje.user_id)
        
        # Generar respuesta incluyendo el contexto
        respuesta = get_response_from_openai(f"{contexto}\nUsuario: {mensaje.message}")
        
        # Guardar la respuesta en el historial
        guardar_contexto(mensaje.user_id, f"Asistente: {respuesta}")
        
        return MessageResponse(response=respuesta)
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))