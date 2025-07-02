import os
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance
from app.openai_service import get_embedding_from_openai  # Debes crear esta función
from app.pdf_processor import procesar_pdf  # Debes crear o tener esta función

# Cargar variables
load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "documentos_pdf")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar cliente Qdrant
client = QdrantClient(url=QDRANT_URL)

def crear_coleccion_si_no_existe():
    if COLLECTION_NAME not in [col.name for col in client.get_collections().collections]:
        logger.info(f"🔧 Creando colección '{COLLECTION_NAME}' en Qdrant...")
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
        )
    else:
        logger.info(f"✅ Colección '{COLLECTION_NAME}' ya existe.")

def cargar_pdf_a_qdrant(path_pdf: str, usuario: str):
    """
    Procesa un PDF, genera embeddings y los sube a Qdrant.
    """
    logger.info(f"📄 Procesando archivo PDF: {path_pdf}")
    crear_coleccion_si_no_existe()

    fragmentos = procesar_pdf(path_pdf)
    logger.info(f"✂️ Fragmentos extraídos: {len(fragmentos)}")

    puntos: List[PointStruct] = []

    for i, fragmento in enumerate(fragmentos):
        texto = fragmento.get("texto", "").strip()
        if not texto:
            continue

        embedding = get_embedding_from_openai(texto)  # Función tuya en openai_service.py

        puntos.append(
            PointStruct(
                id=str(uuid4()),
                vector=embedding,
                payload={
                    "texto": texto,
                    "usuario": usuario,
                    "fragmento_n": i,
                    "fuente": os.path.basename(path_pdf),
                    "num_tokens": fragmento.get("num_tokens", 0)
                }
            )
        )

    if puntos:
        logger.info(f"📤 Subiendo {len(puntos)} vectores a Qdrant...")
        client.upsert(collection_name=COLLECTION_NAME, points=puntos)
        logger.info("✅ Vectorización y carga completadas.")
    else:
        logger.warning("⚠️ No se generaron puntos para cargar a Qdrant")

def buscar_en_documentos(consulta: str, usuario: str, top_k: int = 3) -> List[Dict]:
    """
    Busca en los documentos cargados por el usuario los fragmentos más relevantes a la consulta.
    
    Args:
        consulta: Texto de la consulta
        usuario: ID del usuario que realizó la consulta
        top_k: Número de resultados a devolver
        
    Returns:
        Lista de diccionarios con los fragmentos más relevantes
    """
    try:
        # Generar embedding para la consulta
        query_embedding = get_embedding_from_openai(consulta)
        
        # Buscar en Qdrant
        search_result = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            query_filter={
                "must": [
                    {"key": "usuario", "match": {"value": usuario}}
                ]
            },
            limit=top_k
        )
        
        # Procesar resultados
        resultados = []
        for hit in search_result:
            if hasattr(hit, 'payload') and hit.payload:
                resultados.append({
                    "texto": hit.payload.get("texto", ""),
                    "score": hit.score,
                    "fuente": hit.payload.get("fuente", "desconocido"),
                    "fragmento_n": hit.payload.get("fragmento_n", 0)
                })
        
        logger.info(f"🔍 Búsqueda completada. Resultados encontrados: {len(resultados)}")
        return resultados
        
    except Exception as e:
        logger.error(f"Error en búsqueda de documentos: {str(e)}", exc_info=True)
        return []
