"""
Servicio para interactuar con la API de WhatsApp Business.
Maneja el envío de mensajes y plantillas a través de la API de Meta.
"""
import os
import json
import logging
import requests
from typing import Dict, Optional, Any
from dotenv import load_dotenv

# Configuración de logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WhatsAppService:
    """Servicio para interactuar con la API de WhatsApp Business."""
    
    def __init__(self):
        """Inicializa el servicio con la configuración de WhatsApp."""
        load_dotenv()
        
        # Configuración de WhatsApp
        self.whatsapp_token = os.getenv("WHATSAPP_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.api_version = os.getenv("WHATSAPP_API_VERSION", "v22.0")
        self.verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")
        
        # Validar configuración
        if not all([self.whatsapp_token, self.phone_number_id]):
            error_msg = "Faltan configuraciones de WhatsApp. Verifica las variables de entorno."
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        logger.info("Servicio de WhatsApp inicializado correctamente")

    def verificar_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verifica el webhook de WhatsApp.
        
        Args:
            mode: Modo de verificación (debe ser 'subscribe')
            token: Token de verificación
            challenge: Challenge a devolver si la verificación es exitosa
            
        Returns:
            str: El challenge si la verificación es exitosa, None en caso contrario
        """
        if mode == 'subscribe' and token == self.verify_token:
            logger.info("Webhook verificado exitosamente")
            return challenge
        logger.warning("Fallo en la verificación del webhook")
        return None

    def enviar_mensaje(self, numero_usuario: str, mensaje: str) -> Dict[str, Any]:
        """
        Envía un mensaje de texto a un número de WhatsApp.
        
        Args:
            numero_usuario: Número de teléfono del destinatario (con código de país)
            mensaje: Contenido del mensaje a enviar
            
        Returns:
            dict: Respuesta de la API de WhatsApp o mensaje de error
        """
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.whatsapp_token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": numero_usuario,
            "type": "text",
            "text": {"body": mensaje}
        }
        
        return self._enviar_peticion(url, headers, data)

    def enviar_template_saludo(self, numero_usuario: str, nombre_usuario: str) -> Dict[str, Any]:
        """
        Envía un mensaje de plantilla de saludo al usuario.
        
        Args:
            numero_usuario: Número de teléfono del destinatario (con código de país)
            nombre_usuario: Nombre del usuario para personalizar el mensaje
            
        Returns:
            dict: Respuesta de la API de WhatsApp o mensaje de error
        """
        try:
            # Validar número de teléfono (debe incluir código de país sin el +)
            if not numero_usuario.isdigit():
                raise ValueError("El número de teléfono solo debe contener dígitos (incluir código de país sin el +)")
                
            # Construir la URL de la API
            url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {self.whatsapp_token.strip()}",
                "Content-Type": "application/json"
            }
            
            # Validar que el token no esté vacío
            if not self.whatsapp_token.strip():
                raise ValueError("El token de WhatsApp no está configurado correctamente")
                
            # Validar que el ID del número de teléfono sea numérico
            if not self.phone_number_id.isdigit():
                raise ValueError("El ID del número de teléfono debe ser un valor numérico")
            
            data = {
                "messaging_product": "whatsapp",
                "to": numero_usuario,
                "type": "template",
                "template": {
                    "name": "magibot_wpp",
                    "language": {"code": "es"},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": nombre_usuario
                                }
                            ]
                        }
                    ]
                }
            }
            
            return self._enviar_peticion(url, headers, data)
            
        except Exception as e:
            logger.error(f"Error al preparar el mensaje de WhatsApp: {str(e)}")
            return {
                "error": True,
                "message": f"Error al preparar el mensaje: {str(e)}",
                "details": str(e)
            }
        
        return self._enviar_peticion(url, headers, data)
    
    def _enviar_peticion(self, url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Envía una petición HTTP a la API de WhatsApp.
        
        Args:
            url: URL del endpoint de la API
            headers: Headers de la petición
            data: Datos a enviar en formato JSON
            
        Returns:
            dict: Respuesta de la API o mensaje de error
        """
        try:
            logger.debug(f"URL: {url}")
            logger.debug(f"Headers: {headers}")
            logger.debug(f"Datos: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            # Log de respuesta exitosa (sin mostrar datos sensibles)
            logger.info("Respuesta exitosa de la API de WhatsApp")
            return response.json()
            
        except requests.exceptions.HTTPError as http_err:
            error_msg = f"Error HTTP {http_err.response.status_code}: {http_err.response.text}"
            logger.error(error_msg)
            return {
                "error": True,
                "message": f"Error en la petición a WhatsApp: {http_err}",
                "status_code": http_err.response.status_code,
                "response": http_err.response.text
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de conexión: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "error": True,
                "message": f"Error de conexión con WhatsApp: {str(e)}",
                "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None,
                "details": str(e)
            }

# Instancia global del servicio
whatsapp_service = WhatsAppService()

# Ejemplo de uso:
if __name__ == "__main__":
    # Ejemplo de envío de mensaje
    resultado = whatsapp_service.enviar_mensaje(
        numero_usuario="1234567890",  # Reemplaza con un número real
        mensaje="¡Hola! Este es un mensaje de prueba."
    )
    print("Resultado del envío:", json.dumps(resultado, indent=2))