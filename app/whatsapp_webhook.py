from fastapi import APIRouter, Request, Body, status, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Optional
import os
import logging
import requests
from dotenv import load_dotenv
from pydantic import BaseModel
from app.openai_service import get_response_from_openai
from app.redis_service import guardar_contexto, obtener_contexto

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
    response_class=PlainTextResponse,
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
        200: {"content": {"text/plain": {"example": "123456789"}}, "description": "Webhook verificado exitosamente"},
        403: {"description": "Token de verificación inválido"}
    }
)
async def verificar_webhook(
    request: Request,
    mode: str = Query(..., alias="hub.mode", description="Modo de verificación (debe ser 'subscribe')"),
    token: str = Query(..., alias="hub.verify_token", description="Token de verificación"),
    challenge: str = Query(..., alias="hub.challenge", description="Challenge para la verificación")
):
    logger.info(f"Token recibido: {token}")
    logger.info(f"Token esperado: {VERIFY_TOKEN}")
    logger.info(f"Modo: {mode}")
    logger.info(f"Challenge: {challenge}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado correctamente con Meta.")
        # Devolver SOLO el challenge como texto plano
        return PlainTextResponse(content=challenge)
    else:
        error_msg = f"❌ Verificación fallida del webhook. Token válido: {token == VERIFY_TOKEN}, Modo correcto: {mode == 'subscribe'}"
        logger.warning(error_msg)
        return PlainTextResponse(content="Forbidden", status_code=403)

@router.post("/webhook")
async def recibir_mensaje(payload: dict = Body(...)):
    """
    Webhook para recibir mensajes de WhatsApp.
    
    Ejemplo de payload esperado:
    {
      "object": "whatsapp_business_account",
      "entry": [{
        "id": "1299981508408074",
        "changes": [{
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "15556406428",
              "phone_number_id": "727974420390128"
            },
            "contacts": [{
              "profile": {"name": "Marcelo Dávila"},
              "wa_id": "59177682259"
            }],
            "messages": [{
              "from": "59177682259",
              "id": "wamid.XXXXX",
              "timestamp": "1751240108",
              "text": {"body": "Hola chatsito"},
              "type": "text"
            }]
          },
          "field": "messages"
        }]
      }]
    }
    """
    try:
        logger.info("📩 Inicio de procesamiento de webhook")
        logger.info(f"📦 Payload recibido: {payload}")
        
        # Verificar si es un mensaje de WhatsApp Business
        if payload.get("object") != "whatsapp_business_account":
            logger.warning("❌ No es un mensaje de WhatsApp Business, ignorando...")
            return {"status": "ok"}
            
        # Extraer el primer entry y changes
        entries = payload.get("entry", [])
        logger.info(f"📋 Número de entradas: {len(entries)}")
        
        if not entries:
            logger.warning("⚠️ No hay entradas en el payload")
            return {"status": "ok"}
            
        entry = entries[0]
        changes = entry.get("changes", [])
        logger.info(f"🔄 Número de cambios: {len(changes)}")
        
        if not changes:
            logger.warning("⚠️ No hay cambios en la entrada")
            return {"status": "ok"}
            
        change = changes[0]
        
        # Verificar si es un mensaje
        if change.get("field") != "messages":
            logger.info(f"ℹ️ No es un mensaje, campo: {change.get('field')}")
            return {"status": "ok"}
            
        value = change.get("value", {})
        messages = value.get("messages", [])
        logger.info(f"💬 Número de mensajes: {len(messages)}")
        
        if not messages:
            logger.info("ℹ️ No hay mensajes en el payload")
            return {"status": "ok"}
        
        # Verificar si hay mensajes
        if not messages:
            logger.info("No hay mensajes en el payload")
            return {"status": "ok"}
            
        mensaje = messages[0]
        
        # Verificar si es un mensaje de texto
        if mensaje.get("type") != "text":
            logger.warning(f"Tipo de mensaje no soportado: {mensaje.get('type')}")
            return {"status": "error", "message": "Solo se soportan mensajes de texto"}
            
        numero = mensaje.get("from")
        texto = mensaje.get("text", {}).get("body")
        
        if not all([numero, texto]):
            logger.error(f"Faltan campos requeridos en el mensaje: {mensaje}")
            return {"status": "error", "message": "Faltan campos requeridos en el mensaje"}
        
        logger.info(f"📱 Mensaje recibido de {numero}: {texto}")
        
        # Guardar el mensaje del usuario en el historial
        guardar_contexto(numero, f"Usuario: {texto}")
        
        # Obtener el historial de la conversación
        contexto = obtener_contexto(numero)
        logger.info(f"📚 Contexto de la conversación: {contexto}")
        
        # Generar respuesta con IA incluyendo el contexto
        respuesta = get_response_from_openai(f"{contexto}\nUsuario: {texto}")
        
        # Guardar la respuesta en el historial
        guardar_contexto(numero, f"Asistente: {respuesta}")
        
        # Enviar respuesta por WhatsApp
        url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Estructura simplificada según la documentación
        data = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": respuesta
            }
        }
        
        logger.info("📤 Enviando mensaje a WhatsApp API")
        logger.debug(f"URL: {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Payload: {data}")
        logger.info(f"Data: {data}")
        
        response = requests.post(url, headers=headers, json=data)
        logger.info(f"Respuesta de WhatsApp API: {response.status_code} - {response.text}")
        
        response.raise_for_status()
        logger.info(f"Respuesta enviada exitosamente a {numero}")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {"status": "error", "message": str(e)}
        
    return {"status": "ok"}