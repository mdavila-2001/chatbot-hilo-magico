# -*- coding: utf-8 -*-
import os
import logging
from typing import Union, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logs
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuración
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek/deepseek-r1:free")

if not OPENROUTER_API_KEY:
    logger.warning("No se encontró OPENROUTER_API_KEY en las variables de entorno")

# Cliente OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY or ""
)

def ensure_unicode(text: Union[str, bytes]) -> str:
    """Convierte texto a string unicode seguro."""
    if isinstance(text, bytes):
        try:
            return text.decode('utf-8')
        except UnicodeDecodeError:
            return text.decode('latin-1', errors='ignore')
    return str(text)

def get_response_from_openai(
    texto: Union[str, bytes],
    model: Optional[str] = None,
    temperature: float = 0.7,
    **kwargs
) -> str:
    """
    Envía texto a la API de OpenRouter y devuelve la respuesta generada.
    
    Args:
        texto: Texto a enviar al modelo
        model: Nombre del modelo a usar (opcional, usa el de configuración por defecto)
        temperature: Controla la aleatoriedad de la respuesta (0-2)
        **kwargs: Argumentos adicionales para la API
        
    Returns:
        str: Respuesta generada por el modelo o mensaje de error
    """
    try:
        if not OPENROUTER_API_KEY:
            error_msg = "No se configuró OPENROUTER_API_KEY"
            logger.error(error_msg)
            return error_msg

        # Procesar texto de entrada
        texto_unicode = ensure_unicode(texto)
        texto_safe = texto_unicode.encode('utf-8', 'ignore').decode('utf-8')
        
        logger.info(f"Enviando petición a OpenRouter (modelo: {model or MODEL_NAME})")

        # Configurar mensajes
        messages = [{"role": "user", "content": texto_safe}]

        # Parámetros de la petición
        params = {
            "model": model or MODEL_NAME,
            "messages": messages,
            "temperature": min(max(0, temperature), 2),  # Asegurar valor entre 0 y 2
            **kwargs
        }

        # Llamar a la API
        response = client.chat.completions.create(**params)

        # Procesar respuesta
        if response and hasattr(response, 'choices') and response.choices:
            result = response.choices[0].message.content
            logger.info("Respuesta recibida exitosamente")
            return result.encode('utf-8', 'ignore').decode('utf-8')

        error_msg = "No se pudo generar una respuesta: respuesta inválida de la API"
        logger.error(error_msg)
        return error_msg

    except Exception as e:
        error_msg = f"Error en get_response_from_openai: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
