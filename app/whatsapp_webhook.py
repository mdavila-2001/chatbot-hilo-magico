from fastapi import APIRouter, Request, Body, status, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import os
import logging
import requests
from dotenv import load_dotenv
from pydantic import BaseModel
from app.openai_service import get_response_from_openai

# Modelos Pydantic para documentación
class WebhookVerificationResponse(BaseModel):
    """Modelo para la respuesta de verificación del webhook"""
    status: str = "ok"
    challenge: Optional[int] = None

class ErrorResponse(BaseModel):
    """Modelo para respuestas de error"""
    status: str
    error: str
    message: Optional[str] = None

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["WhatsApp"],
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Parámetros inválidos"},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "No autorizado"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Error interno del servidor"}
    }
)

# Variables de entorno
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "aEpi35bfwk8emyCR2ZDdcv19PlrN06xA")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")

@router.get(
    "/webhook",
    response_model=WebhookVerificationResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Verificar Webhook",
    description="""
    Endpoint para la verificación del webhook de WhatsApp Business API.
    
    Este endpoint es llamado por Meta durante el proceso de configuración del webhook
    para verificar la propiedad del servidor.
    
    - **mode**: Debe ser 'subscribe'
    - **token**: Token de verificación configurado en el dashboard de Meta
    - **challenge**: Cadena aleatoria que debe ser devuelta para la verificación
    """,
    responses={
        200: {"description": "Webhook verificado exitosamente"},
        403: {"description": "Token de verificación inválido"}
    }
)
async def verificar_webhook(
    request: Request,
    mode: str = Query(..., alias="hub.mode", description="Modo de verificación (debe ser 'subscribe')"),
    token: str = Query(..., alias="hub.verify_token", description="Token de verificación"),
    challenge: str = Query(..., alias="hub.challenge", description="Challenge para la verificación")
):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    logger.info(f"Token recibido: {token}")
    logger.info(f"Token esperado: {VERIFY_TOKEN}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado correctamente con Meta.")
        return {"status": "ok", "challenge": int(challenge)}
    else:
        logger.warning("❌ Verificación fallida del webhook.")
        return {"status": "Forbidden"}, 403

@router.post("/webhook")
async def recibir_mensaje(payload: dict = Body(...)):
    """
    Webhook para recibir mensajes de WhatsApp.
    
    Ejemplo de payload esperado:
    {
      "entry": [{
        "changes": [{
          "value": {
            "messages": [{
              "from": "59171234567",
              "text": {"body": "Mensaje de prueba"}
            }]
          }
        }]
      }]
    }
    """
    try:
        # Extraer datos del mensaje
        mensaje = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        numero = mensaje["from"]
        texto = mensaje["text"]["body"]
        
        logger.info(f"Mensaje de {numero}: {texto}")
        
        # Generar respuesta con IA
        respuesta = get_response_from_openai(texto)
        
        # Enviar respuesta por WhatsApp
        url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
            "Content-Type": "application/json"
        }
        # Estructura simple para mensaje de texto directo
        data = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {
                "body": respuesta
            }
        }
        
        logger.info(f"Enviando a WhatsApp API:")
        logger.info(f"URL: {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Data: {data}")
        
        response = requests.post(url, headers=headers, json=data)
        logger.info(f"Respuesta de WhatsApp API: {response.status_code} - {response.text}")
        
        response.raise_for_status()
        logger.info(f"Respuesta enviada exitosamente a {numero}")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {"status": "error", "message": str(e)}
        
    return {"status": "ok"}