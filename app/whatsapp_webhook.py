from fastapi import APIRouter, Request, Body, status, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import os
import logging
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.openai_service import get_response_from_openai

# Cargar variables de entorno
load_dotenv()

VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "aEpi35bfwk8emyCR2ZDdcv19PlrN06xA")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")

router = APIRouter(tags=["WhatsApp"])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.get("/webhook")
async def verificar_webhook(
    request: Request,
    mode: str = Query(..., alias="hub.mode"),
    token: str = Query(..., alias="hub.verify_token"),
    challenge: str = Query(..., alias="hub.challenge")
):
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado con Meta.")
        return {"status": "ok", "challenge": int(challenge)}
    else:
        logger.warning("❌ Token de verificación inválido.")
        return JSONResponse(status_code=403, content={"status": "Forbidden"})

class SimpleMessage(BaseModel):
    """Modelo simplificado para mensajes de WhatsApp"""
    from_number: str = Field(..., alias="from")
    text: str = Field(..., description="Texto del mensaje")

@router.post("/webhook")
async def recibir_mensaje(message: SimpleMessage):
    try:
        numero = message.from_number
        texto = message.text
        
        logger.info(f"📨 Mensaje de {numero}: {texto}")

        # Obtener respuesta del asistente
        respuesta = get_response_from_openai(texto)
        logger.info(f"🤖 Respuesta generada: {respuesta}")

        # Enviar respuesta por WhatsApp
        url = f"https://graph.facebook.com/v22.0/727974420390128/messages"
        headers = {
            "Authorization": f"Bearer EAAKbtcSZCAY4BO9AL0DPPfBsXx75bg8ZCsZCIJP5iaZAjRywcnV2Fhh8IhoazM6UVU0tUHQ4OhRYVkMaHBBPHIpZCgWdqCXXpDNTFgWT3tFfzIZBt8xTjLM5ZCNhEuIPkJg1wTre8bfLEnsokSRiB7sGHgRnm33LZBrwDzRn2Hr9YzQZBaTmP88PBy00y0qWbPfkzPZAzqkrEY9FsZAZBxK00gbNktUT3zsVlUL9miAgO2iZB8k3XVZCYZD",
            "Content-Type": "application/json"
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {
                "body": respuesta
            }
        }

        logger.info("📤 Enviando respuesta a WhatsApp...")
        logger.info(f"URL: {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Datos: {data}")
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            logger.info(f"Código de estado: {response.status_code}")
            logger.info(f"Respuesta en bruto: {response.text}")
            
            response_data = response.json()
            
            if response.status_code == 200:
                message_id = response_data.get('messages', [{}])[0].get('id')
                logger.info(f"✅ Mensaje enviado exitosamente a {numero}. ID: {message_id}")
                return {
                    "status": "ok",
                    "response": respuesta,
                    "to": numero,
                    "message_id": message_id,
                    "whatsapp_response": response_data
                }
            else:
                error_msg = f"❌ Error al enviar mensaje: {response.status_code} - {response_data}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "to": numero,
                    "whatsapp_response": response_data
                }
                
        except requests.exceptions.RequestException as e:
            error_msg = f"❌ Error en la petición a WhatsApp: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "message": error_msg,
                "to": numero
            }

    except Exception as e:
        logger.error(f"❌ Error en el webhook: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error al procesar el mensaje: {str(e)}"
        }
