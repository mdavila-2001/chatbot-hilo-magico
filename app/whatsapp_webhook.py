from fastapi import APIRouter, Request, Body, status, HTTPException, Query
from fastapi.responses import PlainTextResponse
from typing import Optional
import os
import logging
import requests
from dotenv import load_dotenv
from pydantic import BaseModel
from app.openai_service import get_response_from_openai
from app.redis_service import guardar_contexto, obtener_contexto
from app.vector_service import cargar_pdf_a_qdrant, buscar_en_documentos
import uuid
import json
from datetime import datetime

# Modelos Pydantic para documentación
class WebhookVerificationResponse(BaseModel):
    status: str = "ok"
    challenge: Optional[int] = None

class ErrorResponse(BaseModel):
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
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse}
    }
)

# Variables de entorno
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERSION = os.getenv("WHATSAPP_API_VERSION", "v17.0")

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
    mode: str = Query(..., alias="hub.mode"),
    token: str = Query(..., alias="hub.verify_token"),
    challenge: str = Query(..., alias="hub.challenge")
):
    logger.info(f"🔐 Verificando webhook: mode={mode}, token={token}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado correctamente.")
        return PlainTextResponse(content=challenge)
    else:
        logger.warning("❌ Verificación fallida del webhook.")
        return PlainTextResponse(content="Forbidden", status_code=403)

@router.post("/webhook")
async def recibir_mensaje(payload: dict = Body(...)):
    """
    Webhook para recibir mensajes de WhatsApp.

    Estructura esperada:
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

        if payload.get("object") != "whatsapp_business_account":
            logger.warning("❌ Payload no corresponde a WhatsApp Business")
            return {"status": "ignored"}

        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            logger.info("ℹ️ No se encontraron mensajes en el payload.")
            return {"status": "ok"}

        mensaje = messages[0]
        tipo = mensaje.get("type")
        numero = mensaje.get("from")

        # ==============================
        # MENSAJES DE TEXTO
        # ==============================
        if tipo == "text":
            texto = mensaje.get("text", {}).get("body")
            
            if not all([numero, texto]):
                logger.error(f"Faltan campos requeridos en el mensaje: {mensaje}")
                return {"status": "error", "message": "Faltan campos requeridos en el mensaje"}

            logger.info(f"📱 Mensaje de texto recibido de {numero}: {texto}")

            # Guardar y obtener contexto
            guardar_contexto(numero, f"Usuario: {texto}")
            contexto = obtener_contexto(numero)
            logger.info(f"📚 Contexto de la conversación: {contexto}")

            # Verificar si hay documentos cargados
            doc_info = obtener_contexto(f"doc_{numero}")
            contexto_documentos = ""
            
            if doc_info:
                try:
                    # Buscar en los documentos cargados
                    resultados = buscar_en_documentos(texto, numero)
                    if resultados:
                        contexto_documentos = "\n\nInformación relevante de documentos:\n" + "\n".join(
                            f"- {res['texto'][:200]}..." for res in resultados[:3]  # Mostrar solo los 3 primeros
                        )
                except Exception as e:
                    logger.error(f"Error buscando en documentos: {str(e)}")
            
            # Generar respuesta con IA incluyendo contexto de documentos
            respuesta = get_response_from_openai(
                f"{contexto}{contexto_documentos}\n\nPregunta del usuario: {texto}"
            )
            guardar_contexto(numero, f"Usuario: {texto}\nAsistente: {respuesta}")

            # Enviar respuesta
            url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
            headers = {
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json"
            }
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

            response = requests.post(url, headers=headers, json=data)
            logger.info(f"Respuesta de WhatsApp API: {response.status_code} - {response.text}")
            response.raise_for_status()
            logger.info(f"✅ Respuesta enviada exitosamente a {numero}")

        # ==============================
        # MENSAJES CON DOCUMENTOS (PDF)
        # ==============================
        elif tipo == "document":
            documento = mensaje.get("document", {})
            media_id = documento.get("id")
            filename = documento.get("filename", "archivo.pdf")

            if not media_id:
                logger.warning("📎 Documento recibido sin media_id")
                return {"status": "ok"}

            logger.info(f"📎 Documento recibido de {numero}: {filename} (media_id: {media_id})")

            # Paso 1: Obtener URL temporal
            media_info_url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{media_id}"
            headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
            media_response = requests.get(media_info_url, headers=headers)
            media_url = media_response.json().get("url")

            if not media_url:
                logger.error("❌ No se pudo obtener la URL del documento")
                return {"status": "error", "message": "Error al obtener documento"}

            # Paso 2: Descargar archivo
            archivo = requests.get(media_url, headers=headers)
            ruta_local = f"./{os.getenv('QDRANT_COLLECTION')}/{filename}"
            os.makedirs(f"./{os.getenv('QDRANT_COLLECTION')}", exist_ok=True)
            with open(ruta_local, "wb") as f:
                f.write(archivo.content)

            logger.info(f"📥 Documento guardado en: {ruta_local}")
            # Procesar el PDF y cargarlo a Qdrant
            try:
                # Asignar un ID único al documento
                doc_id = str(uuid.uuid4())
                # Cargar el PDF a Qdrant
                cargar_pdf_a_qdrant(ruta_local, numero)
                
                # Guardar información del documento en el contexto
                guardar_contexto(
                    f"doc_{numero}", 
                    json.dumps({
                        "documento": filename,
                        "fecha": datetime.now().isoformat()
                    })
                )
                
                # Enviar confirmación al usuario
                mensaje_respuesta = f"✅ Documento '{filename}' procesado correctamente. Ya puedes hacer preguntas sobre él."
                
            except Exception as e:
                logger.error(f"Error procesando PDF: {str(e)}", exc_info=True)
                mensaje_respuesta = "❌ Lo siento, hubo un error al procesar el documento. Por favor, inténtalo de nuevo."
            
            # Enviar respuesta al usuario
            url = f"https://graph.facebook.com/{WHATSAPP_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
            headers = {
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json"
            }
            data = {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "text",
                "text": {
                    "body": mensaje_respuesta
                }
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            return {"status": "documento_procesado", "archivo": filename}

        # ==============================
        # OTRO TIPO DE MENSAJE
        # ==============================
        else:
            logger.info(f"🪪 Tipo de mensaje no soportado aún: {tipo}")
            return {"status": "unsupported", "type": tipo}

    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

    return {"status": "ok"}
