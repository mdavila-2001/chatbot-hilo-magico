import os
import logging
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue,
    CollectionStatus, UpdateStatus, OptimizersConfigDiff
)
from app.openai_service import get_embedding_from_openai
from app.pdf_processor import procesar_pdf

# Cargar variables de entorno
load_dotenv()

# Configuración
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "documentos_pdf_optimizado")
VECTOR_SIZE = 1024  # Tamaño del embedding de DeepSeek
BATCH_SIZE = 32  # Tamaño del lote para procesamiento por lotes
SIMILARITY_THRESHOLD = 0.75  # Umbral de similitud mínimo

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicializar cliente Qdrant con configuración optimizada
client = QdrantClient(
    url=QDRANT_URL,
    timeout=30.0,
    prefer_grpc=True  # Usar gRPC para mejor rendimiento
)

def generar_id_unico(texto: str, usuario: str) -> int:
    """Genera un ID único para un documento basado en su contenido y usuario."""
    return int(hashlib.sha256(f"{usuario}_{texto}".encode()).hexdigest()[:15], 16)

def crear_coleccion_optimizada():
    """Crea una colección optimizada para búsquedas semánticas."""
    try:
        # Verificar si la colección ya existe
        collections = client.get_collections()
        collection_names = [col.name for col in collections.collections]
        
        if COLLECTION_NAME in collection_names:
            logger.info(f"✅ Colección '{COLLECTION_NAME}' ya existe.")
            return True
            
        logger.info(f"🔧 Creando colección optimizada '{COLLECTION_NAME}'...")
        
        # Configuración optimizada para la colección
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
                on_disk=True  # Almacenar vectores en disco para ahorrar RAM
            ),
            optimizers_config=OptimizersConfigDiff(
                deleted_threshold=0.5,
                vacuum_min_vector_number=1000,
                default_segment_number=2,
                max_segment_size=50000,
                memmap_threshold=20000,
                indexing_threshold=20000,
                flush_interval_sec=5,
                max_optimization_threads=4
            ),
            hnsw_config=models.HnswConfigDiff(
                m=16,  # Número de conexiones por nodo (16-64)
                ef_construct=200,  # Tamaño de la lista dinámica para la construcción
                full_scan_threshold=10000,  # Número de puntos para escaneo completo
                payload_m=16  # Número de conexiones para el índice de carga útil
            ),
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type="int8",
                    quantile=0.99,
                    always_ram=True
                )
            )
        )
        
        logger.info(f"✅ Colección '{COLLECTION_NAME}' creada con configuración optimizada.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al crear la colección: {str(e)}")
        return False

def indexar_documento(texto: str, metadata: dict, usuario: str) -> bool:
    """
    Indexa un fragmento de texto en Qdrant con metadatos.
    
    Args:
        texto: Texto a indexar
        metadata: Metadatos adicionales
        usuario: ID del usuario propietario
        
    Returns:
        bool: True si se indexó correctamente
    """
    try:
        # Verificar y crear colección si es necesario
        if not crear_coleccion_optimizada():
            return False
        
        # Generar embedding
        embedding = get_embedding_from_openai(texto)
        
        # Crear punto con metadatos
        punto = PointStruct(
            id=generar_id_unico(texto, usuario),
            vector=embedding,
            payload={
                "texto": texto,
                "usuario": usuario,
                "timestamp": datetime.utcnow().isoformat(),
                **metadata
            }
        )
        
        # Insertar en lote (más eficiente)
        client.upsert(
            collection_name=COLLECTION_NAME,
            wait=True,
            points=[punto]
        )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al indexar documento: {str(e)}")
        return False

def indexar_documento_lote(textos: List[str], metadatos: List[dict], usuario: str) -> bool:
    """
    Indexa múltiples fragmentos de texto en un solo lote.
    
    Args:
        textos: Lista de textos a indexar
        metadatos: Lista de diccionarios con metadatos
        usuario: ID del usuario propietario
        
    Returns:
        bool: True si se indexó correctamente
    """
    try:
        if not textos or len(textos) != len(metadatos):
            logger.error("❌ Número de textos y metadatos no coincide")
            return False
            
        # Verificar y crear colección si es necesario
        if not crear_coleccion_optimizada():
            return False
        
        puntos = []
        
        # Procesar en lotes para evitar sobrecarga de memoria
        for i in range(0, len(textos), BATCH_SIZE):
            batch_texts = textos[i:i+BATCH_SIZE]
            batch_metas = metadatos[i:i+BATCH_SIZE]
            
            # Generar embeddings por lote
            batch_embeddings = [
                get_embedding_from_openai(texto) 
                for texto in batch_texts
            ]
            
            # Crear puntos del lote
            for j, (texto, embedding) in enumerate(zip(batch_texts, batch_embeddings)):
                punto = PointStruct(
                    id=generar_id_unico(f"{texto}_{i+j}", usuario),
                    vector=embedding,
                    payload={
                        "texto": texto,
                        "usuario": usuario,
                        "timestamp": datetime.utcnow().isoformat(),
                        **batch_metas[j]
                    }
                )
                puntos.append(punto)
                
                # Insertar si alcanzamos el tamaño del lote
                if len(puntos) >= BATCH_SIZE:
                    client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=puntos,
                        wait=False  # No esperar confirmación para mejor rendimiento
                    )
                    puntos = []
        
        # Insertar puntos restantes
        if puntos:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=puntos,
                wait=True  # Esperar a que termine el último lote
            )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en indexación por lotes: {str(e)}")
        return False

def cargar_pdf_a_qdrant(path_pdf: str, usuario: str) -> dict:
    """
    Procesa un PDF, genera embeddings y los sube a Qdrant de forma optimizada.
    
    Args:
        path_pdf: Ruta al archivo PDF a procesar
        usuario: ID del usuario propietario del documento
        
    Returns:
        dict: Estadísticas del proceso con la siguiente estructura:
            {
                'total_fragmentos': int,
                'fragmentos_procesados': int,
                'exito': bool,
                'mensaje': str
            }
    """
    logger.info(f"📄 Procesando archivo PDF: {path_pdf}")
    
    # Inicializar estadísticas
    estadisticas = {
        'total_fragmentos': 0,
        'fragmentos_procesados': 0,
        'exito': False,
        'mensaje': ''
    }
    
    try:
        # Extraer y limpiar fragmentos del PDF
        fragmentos = procesar_pdf(path_pdf)
        if not fragmentos:
            raise ValueError("No se pudieron extraer fragmentos del PDF")
        
        estadisticas['total_fragmentos'] = len(fragmentos)
        logger.info(f"✂️ Fragmentos extraídos: {estadisticas['total_fragmentos']}")
        
        # Preparar datos para indexación por lotes
        textos = []
        metadatos = []
        
        # Procesar cada fragmento del PDF
        for i, fragmento in enumerate(fragmentos):
            texto = fragmento.get("texto", "").strip()
            if not texto:
                continue
                
            textos.append(texto)
            metadatos.append({
                "fuente": os.path.basename(path_pdf),
                "pagina": fragmento.get("pagina", i + 1),
                "fragmento_id": i + 1,
                "num_tokens": fragmento.get("num_tokens", 0)
            })
        
        # Verificar que hay textos para procesar
        if not textos:
            raise ValueError("No se encontró texto válido en el PDF")
        
        # Indexar los fragmentos en lotes
        exito = indexar_documento_lote(textos, metadatos, usuario)
        
        if exito:
            estadisticas['fragmentos_procesados'] = len(textos)
            estadisticas['exito'] = True
            estadisticas['mensaje'] = f"Se procesaron {len(textos)} fragmentos correctamente"
            logger.info(estadisticas['mensaje'])
        else:
            raise Exception("Error al indexar los fragmentos del PDF")
            
    except FileNotFoundError as e:
        mensaje = f"Error: Archivo no encontrado - {str(e)}"
        logger.error(mensaje)
        estadisticas['mensaje'] = mensaje
    except ValueError as e:
        mensaje = f"Error de valor: {str(e)}"
        logger.error(mensaje)
        estadisticas['mensaje'] = mensaje
    except Exception as e:
        mensaje = f"Error inesperado al procesar el PDF: {str(e)}"
        logger.error(mensaje, exc_info=True)
        estadisticas['mensaje'] = mensaje
    
    return estadisticas

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

def buscar_documentos_similares(
    consulta: str, 
    usuario: str, 
    top_k: int = 3,
    score_minimo: float = None,
    filtros_adicionales: dict = None
) -> List[Dict[str, Any]]:
    """
    Realiza una búsqueda semántica optimizada en los documentos del usuario.
    
    Args:
        consulta: Texto de la consulta
        usuario: ID del usuario propietario de los documentos
        top_k: Número máximo de resultados a devolver
        score_minimo: Umbral de similitud mínimo (0-1)
        filtros_adicionales: Filtros adicionales para la búsqueda
        
    Returns:
        Lista de documentos coincidentes con sus puntuaciones
    """
    try:
        # Establecer umbral de similitud si no se proporciona
        if score_minimo is None:
            score_minimo = SIMILARITY_THRESHOLD
        
        logger.info(f"🔍 Buscando documentos para usuario '{usuario}': {consulta[:50]}...")
        
        # Generar embedding de la consulta
        query_embedding = get_embedding_from_openai(consulta)
        
        # Construir filtros
        must_conditions = [
            FieldCondition(
                key="usuario",
                match=MatchValue(value=usuario)
            )
        ]
        
        # Añadir filtros adicionales si existen
        if filtros_adicionales:
            for key, value in filtros_adicionales.items():
                must_conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value)
                    )
                )
        
        # Realizar búsqueda con filtros
        search_results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            query_filter=Filter(must=must_conditions),
            limit=top_k * 2,  # Buscar más para filtrar después
            with_vectors=False,
            with_payload=True,
            score_threshold=score_minimo
        )
        
        # Procesar resultados
        resultados = []
        for hit in search_results:
            # Filtrar por puntuación mínima
            if hit.score >= score_minimo:
                resultados.append({
                    "texto": hit.payload.get("texto", ""),
                    "score": float(hit.score),  # Convertir a float nativo
                    "metadatos": {
                        "fuente": hit.payload.get("fuente", "desconocido"),
                        "pagina": hit.payload.get("pagina", 0),
                        "fragmento_id": hit.payload.get("fragmento_id"),
                        "timestamp": hit.payload.get("timestamp")
                    }
                })
        
        # Ordenar por puntuación (mayor a menor) y limitar resultados
        resultados.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"✅ Encontrados {len(resultados)} resultados relevantes")
        return resultados[:top_k]
        
    except Exception as e:
        logger.error(f"❌ Error en búsqueda semántica: {str(e)}", exc_info=True)
        return []

def buscar_por_similitud(
    texto_referencia: str,
    usuario: str,
    top_k: int = 3,
    campos_retorno: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Busca documentos similares a un texto de referencia.
    
    Args:
        texto_referencia: Texto de referencia para la búsqueda
        usuario: ID del usuario propietario
        top_k: Número máximo de resultados
        campos_retorno: Campos específicos a retornar
        
    Returns:
        Lista de documentos similares
    """
    try:
        # Generar embedding del texto de referencia
        referencia_embedding = get_embedding_from_openai(texto_referencia)
        
        # Realizar búsqueda por similitud
        resultados = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=referencia_embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="usuario",
                        match=MatchValue(value=usuario)
                    )
                ]
            ),
            limit=top_k,
            with_vectors=False,
            with_payload=campos_retorno or True,
            score_threshold=SIMILARITY_THRESHOLD
        )
        
        # Formatear resultados
        return [
            {
                "id": str(hit.id),
                "score": float(hit.score),
                **hit.payload
            }
            for hit in resultados
        ]
        
    except Exception as e:
        logger.error(f"Error en búsqueda por similitud: {str(e)}")
        return []

def buscar_por_metadatos(
    usuario: str,
    filtros: Dict[str, Any],
    top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Busca documentos por metadatos exactos.
    
    Args:
        usuario: ID del usuario propietario
        filtros: Diccionario con los campos y valores a filtrar
        top_k: Número máximo de resultados
        
    Returns:
        Lista de documentos que coinciden con los filtros
    """
    try:
        must_conditions = [
            FieldCondition(
                key="usuario",
                match=MatchValue(value=usuario)
            )
        ]
        
        # Añadir filtros adicionales
        for key, value in filtros.items():
            must_conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=value)
                )
            )
        
        # Realizar búsqueda
        resultados = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=must_conditions),
            limit=top_k,
            with_vectors=False,
            with_payload=True
        )
        
        return [
            {
                "id": str(hit.id),
                **hit.payload
            }
            for hit in resultados[0]  # scroll devuelve una tupla (resultados, offset)
        ]
        
    except Exception as e:
        logger.error(f"Error en búsqueda por metadatos: {str(e)}")
        return []

def eliminar_documentos_usuario(usuario: str) -> bool:
    """
    Elimina todos los documentos de un usuario.
    
    Args:
        usuario: ID del usuario
        
    Returns:
        bool: True si se eliminaron correctamente
    """
    try:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="usuario",
                            match=MatchValue(value=usuario)
                        )
                    ]
                )
            )
        )
        logger.info(f"✅ Documentos del usuario '{usuario}' eliminados correctamente")
        return True
    except Exception as e:
        logger.error(f"❌ Error al eliminar documentos: {str(e)}")
        return False
