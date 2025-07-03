# app/embedding_service.py

from sentence_transformers import SentenceTransformer
import logging
import os

# Cargar modelo liviano local
model = SentenceTransformer(os.getenv("EMBEDDING_MODEL"))

# Logger
logger = logging.getLogger(__name__)

def get_embedding_local(texto: str) -> list[float]:
    try:
        logger.info("🔢 Generando embedding localmente...")
        vector = model.encode(texto).tolist()
        return vector
    except Exception as e:
        logger.error(f"❌ Error al generar embedding local: {str(e)}")
        raise RuntimeError("Error al generar embedding local.")
