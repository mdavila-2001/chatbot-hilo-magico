# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import router as api_router
import uvicorn
from app.whatsapp_webhook import router as whatsapp_router

# Cargar variables de entorno
load_dotenv()

# Configuración de la aplicación FastAPI
app = FastAPI(
    title=os.getenv("APP_NAME", "Chatbot Hilo Mágico"),
    description=os.getenv("APP_DESCRIPTION", "API para el chatbot de Hilo Mágico"),
    version=os.getenv("APP_VERSION", "1.0.0"),
    openapi_tags=[{"name": "Chat", "description": "Endpoints para el chat con IA"}],
    debug=os.getenv("DEBUG", "False").lower() == "true"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=os.getenv("ALLOW_CREDENTIALS", "True").lower() == "true",
    allow_methods=os.getenv("ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("ALLOW_HEADERS", "*").split(","),
)

# Incluir rutas del router
app.include_router(api_router, prefix=os.getenv("API_PREFIX", "/api"))
app.include_router(whatsapp_router, prefix=os.getenv("API_PREFIX", "/api"))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("DEBUG", "False").lower() == "true"
    )