from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import logging
from app.openai_service import get_response_from_openai

router = APIRouter(tags=["Chat"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageRequest(BaseModel):
    user_id: str = Field(..., description="ID del usuario")
    message: str = Field(..., description="Mensaje enviado por el usuario")

class MessageResponse(BaseModel):
    response: str

@router.post("/responder", response_model=MessageResponse)
async def responder(mensaje: MessageRequest):
    try:
        logger.info(f"📨 Mensaje de {mensaje.user_id}: {mensaje.message}")
        respuesta = get_response_from_openai(mensaje.message)
        return MessageResponse(response=respuesta)
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))