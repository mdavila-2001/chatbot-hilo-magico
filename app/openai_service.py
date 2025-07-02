# -*- coding: utf-8 -*-
import os
import logging
import json
from typing import Union, Dict, Any, List
from dotenv import load_dotenv
from openai import OpenAI
import httpx

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_openai_client():
    """Crea y retorna un cliente de OpenAI con configuración segura."""
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        http_client=httpx.Client(
            headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Hilo Magico Chatbot"
            },
            timeout=30.0
        )
    )

client = get_openai_client()

def sanitize_text(text: Union[str, bytes]) -> str:
    """
    Limpia y asegura que el texto sea UTF-8 válido, manteniendo caracteres en español.
    
    Args:
        text: Texto a limpiar (puede ser str o bytes)
        
    Returns:
        str: Texto limpio con codificación UTF-8 válida
    """
    if not text:
        return ""
        
    # Convertir a string si es necesario
    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = text.decode('latin-1')
            except Exception:
                text = str(text, errors='replace')
    
    # Asegurar que sea string
    text = str(text)
    
    # Reemplazar caracteres de control pero mantener caracteres especiales
    import re
    # Eliminar caracteres de control (0x00-0x1F, 0x7F-0x9F) excepto saltos de línea
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    return text.strip()

def get_response_from_openai(texto: Union[str, bytes], temperature: float = 0.7) -> str:
    """
    Envía un mensaje al modelo de lenguaje y devuelve la respuesta.
    
    Args:
        texto: Texto del usuario
        temperature: Temperatura del modelo IA (0.0 a 1.0)
    
    Returns:
        str: Respuesta del modelo o mensaje de error.
    """
    try:
        # Limpiar y asegurar el texto de entrada
        texto_limpio = sanitize_text(texto)
        logger.info("Enviando petición a OpenRouter")
        
        # Crear mensaje con rol de sistema
        system_msg = {
            "role": "system",
            #"content": "Eres un asistente útil llamado MagiBot que ayuda a los clientes de Hilo Mágico."
            "content": "Eres un asistente útil que responde preguntas de manera concisa y amable."
        }
        
        # Crear mensaje del usuario
        user_msg = {
            "role": "user",
            "content": texto_limpio
        }
        
        # Realizar la petición a la API
        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME"),
            messages=[system_msg, user_msg],
            temperature=min(max(0.0, float(temperature)), 1.0),  # Asegurar valor entre 0 y 1
        )
        
        # Procesar la respuesta
        if response and hasattr(response, 'choices') and response.choices:
            result = response.choices[0].message.content
            if result:
                return sanitize_text(result)
            
        logger.warning("No se pudo generar una respuesta válida")
        return "No pude generar una respuesta en este momento. ¿Podrías reformular tu pregunta?"
        
    except Exception as e:
        logger.error(f"Error en la API: {str(e)}", exc_info=True)
        return "Ocurrió un error al procesar tu solicitud. Por favor, inténtalo de nuevo."

# =========================
# GENERAR EMBEDDINGS
# =========================

def get_embedding_from_openai(texto: str) -> List[float]:
    """
    Genera un embedding a partir de texto usando un modelo compatible con OpenRouter.
    
    Args:
        texto: Texto para el cual generar el embedding
        
    Returns:
        List[float]: Vector de embedding
    """
    try:
        texto_limpio = sanitize_text(texto)
        logger.info("🧬 Generando embedding para texto...")

        # Lista de modelos de embedding a probar (en orden de preferencia)
        embedding_models = [
            "text-embedding-3-small",  # Modelo de embedding de OpenAI más reciente
            "text-embedding-ada-002",  # Modelo de embedding de OpenAI anterior
            "sentence-transformers/all-mpnet-base-v2",  # Alternativa popular
            "hkunlp/instructor-large"  # Otra alternativa
        ]

        last_error = None
        
        for model in embedding_models:
            try:
                logger.info(f"🔍 Probando modelo de embedding: {model}")
                response = client.embeddings.create(
                    input=texto_limpio,
                    model=model
                )

                if response and hasattr(response, 'data') and response.data:
                    logger.info(f"✅ Modelo {model} funcionó correctamente")
                    return response.data[0].embedding
                    
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ El modelo {model} falló: {str(e)}")
                continue

        # Si llegamos aquí, ningún modelo funcionó
        if last_error:
            logger.error("❌ Todos los modelos de embedding fallaron", exc_info=True)
            raise RuntimeError(f"No se pudo generar el embedding con ningún modelo. Último error: {str(last_error)}")
        else:
            raise RuntimeError("No se pudo generar el embedding: respuesta de la API vacía")

    except Exception as e:
        logger.error(f"❌ Error al generar embedding: {str(e)}", exc_info=True)
        raise RuntimeError(f"No se pudo generar el embedding: {str(e)}")