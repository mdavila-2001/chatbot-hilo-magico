# app/vector_service.py

import os
import logging
import fitz  # PyMuPDF
from uuid import uuid4
from typing import List
from app.embedding_service import get_embedding_local  # Embedding local
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, VectorParams, Distance, Filter, FieldCondition, MatchValue
)

# Logger
logger = logging.getLogger(__name__)

# Configuración de Qdrant
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "pdf_docs"

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Crear colección si no existe
if COLLECTION_NAME not in [col.name for col in qdrant.get_collections().collections]:
    qdrant.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )
    logger.info(f"📦 Colección '{COLLECTION_NAME}' creada.")
else:
    logger.info(f"✅ Colección '{COLLECTION_NAME}' ya existe.")

def extraer_texto_pdf(ruta_pdf: str) -> List[str]:
    """Extrae y fragmenta el texto de un PDF"""
    doc = fitz.open(ruta_pdf)
    texto_completo = "\n".join(pagina.get_text() for pagina in doc)
    doc.close()

    # Fragmentar en párrafos (mínimo 40 caracteres)
    fragmentos = [p.strip() for p in texto_completo.split("\n") if len(p.strip()) >= 40]
    logger.info(f"✂️ Fragmentos extraídos: {len(fragmentos)}")
    return fragmentos

def cargar_pdf_a_qdrant(ruta_pdf: str, user_id: str):
    """Carga un PDF a Qdrant con embeddings locales"""
    logger.info(f"📄 Procesando PDF: {ruta_pdf}")
    fragmentos = extraer_texto_pdf(ruta_pdf)

    puntos = []
    for i, frag in enumerate(fragmentos):
        vector = get_embedding_local(frag)
        puntos.append(PointStruct(
            id=uuid4().int >> 64,
            vector=vector,
            payload={
                "user_id": user_id,
                "fragmento": frag,
                "archivo": os.path.basename(ruta_pdf),
                "pos": i
            }
        ))

    qdrant.upsert(collection_name=COLLECTION_NAME, points=puntos)
    logger.info(f"✅ Insertados {len(puntos)} fragmentos para el usuario {user_id}.")

def buscar_en_documentos(pregunta: str, user_id: str, top_k: int = 5) -> List[dict]:
    """Busca fragmentos relevantes en Qdrant dados los embeddings"""
    vector = get_embedding_local(pregunta)

    resultados = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        limit=top_k,
        query_filter=Filter(
            must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id))
            ]
        )
    )

    return [
        {"texto": punto.payload.get("fragmento"), "score": punto.score}
        for punto in resultados if punto.payload.get("fragmento")
    ]
