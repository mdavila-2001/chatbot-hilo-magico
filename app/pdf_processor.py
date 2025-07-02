import os
import fitz  # PyMuPDF
import tiktoken
from typing import List, Dict, Any
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class PDFProcessor:
    def __init__(self):
        # Usar MODEL_NAME del entorno (el mismo que para OpenAI)
        self.model_name = os.getenv("MODEL_NAME")
        self.max_tokens = int(os.getenv("PDF_MAX_TOKENS", "400"))
        self.overlap_tokens = int(os.getenv("PDF_OVERLAP_TOKENS", "50"))
        self.encoding = self._get_encoding()

    def _get_encoding(self):
        try:
            return tiktoken.encoding_for_model(self.model_name)
        except:
            return tiktoken.get_encoding("cl100k_base")

    def contar_tokens(self, texto: str) -> int:
        """Cuenta los tokens usando el mismo modelo que la API de OpenAI"""
        return len(self.encoding.encode(texto))

    def dividir_texto_en_fragmentos(self, texto: str) -> List[str]:
        """Divide el texto en fragmentos manejables con superposición controlada"""
        palabras = texto.split()
        fragmentos = []
        paso = self.max_tokens - self.overlap_tokens

        for i in range(0, len(palabras), paso):
            fragmento = " ".join(palabras[i:i + self.max_tokens])
            fragmentos.append(fragmento)

        return fragmentos

    def procesar_pdf(self, ruta_pdf: str) -> List[Dict[str, Any]]:
        """Procesa un PDF y devuelve fragmentos con metadatos"""
        try:
            doc = fitz.open(ruta_pdf)
            texto_total = " ".join(
                page.get_text().replace("\n", " ").strip() 
                for page in doc
            )
            
            fragmentos = []
            for i, fragmento in enumerate(self.dividir_texto_en_fragmentos(texto_total), 1):
                fragmentos.append({
                    "texto": fragmento,
                    "num_tokens": self.contar_tokens(fragmento),
                    "origen": os.path.basename(ruta_pdf),
                    "fragmento_id": i
                })
            
            return fragmentos
            
        except Exception as e:
            print(f"Error procesando PDF {ruta_pdf}: {str(e)}")
            return []
        finally:
            if 'doc' in locals():
                doc.close()

# Instancia global para uso directo
processor = PDFProcessor()

# Funciones de conveniencia (opcionales, para compatibilidad)
contar_tokens = processor.contar_tokens
procesar_pdf = processor.procesar_pdf