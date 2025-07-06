import logging
from api.middleware.log import APIGatewayMiddleware
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.constant.config import (
    ENABLE_TRACING,
    SECRET_KEY
)

from api.routers import auth, asl
from starlette.middleware.sessions import SessionMiddleware
from api.database.database import session_manager
from contextlib import asynccontextmanager
from api.middleware.auth import get_current_user
from prometheus_fastapi_instrumentator import Instrumentator

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.sdk.resources import Resource

from api.utils.tracer import configure_tracing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize tracing if enabled - MUST happen before app creation
tracer = None
logger.info(f"ENABLE_TRACING setting: {ENABLE_TRACING}")
if ENABLE_TRACING.lower() == "true":
    logger.info(f"[TRACING] Initializing tracing for service: {ENABLE_TRACING}")
    tracer = configure_tracing()
    logger.info(f"[TRACING] Tracer configured: {type(tracer)}")
    
    # Initialize instrumentation immediately
    RequestsInstrumentor().instrument()
    PymongoInstrumentor().instrument()
    logger.info("[TRACING] Instrumentation configured")

@asynccontextmanager
async def lifespan(app: FastAPI):  
    # Initialize MongoDB collections
    await session_manager.create_collections([
        "users"
    ])
    
    yield
    
    # Close MongoDB connection when app shuts down
    if session_manager.client is not None:
        await session_manager.close()
        
app = FastAPI(lifespan=lifespan, root_path="/api")

# Instrument FastAPI after app creation but before adding middleware
if tracer:
    FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())
    logger.info("[TRACING] FastAPI instrumentation applied")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow all origins
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Add session middleware for managing server-side sessions
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.add_middleware(APIGatewayMiddleware)

# Add a basic health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint to verify the API is running."""
    if tracer:
        with tracer.start_as_current_span("health_check") as span:
            span.set_attribute("health.status", "ok")
            span.set_attribute("database.type", "mongodb")
            span.set_attribute("tracing.enabled", True)
            return {"status": "ok", "database": "mongodb", "tracing": "enabled"}
    return {"status": "ok", "database": "mongodb", "tracing": "disabled"}

# Include routers with authentication where needed
app.include_router(auth.router)
app.include_router(asl.router)

# Add Prometheus metrics endpoint (exclude /metrics from tracing to avoid noise)
Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app)
