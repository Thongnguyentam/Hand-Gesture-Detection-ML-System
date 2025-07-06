import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = "gpt-4o-mini"
OPENAI_API_KEY= os.getenv("OPENAI_API_KEY")
SECRET_KEY= os.getenv("SECRET_KEY")
MONGODB_CONNECTION_URL = os.getenv("MONGODB_CONNECTION_URL")
JWT_SECRET= os.getenv("JWT_SECRET")

# Production flag
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# Host and port for uvicorn server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))


# Jaeger
# Disable tracing by default, especially during tests
ENABLE_TRACING= os.getenv("ENABLE_TRACING", "false")

# Direct connection to Jaeger Collector (bypassing agent)
JAEGER_COLLECTOR_HOST= os.getenv("JAEGER_COLLECTOR_HOST", "jaeger-collector.tracing.svc.cluster.local")
JAEGER_AGENT_PORT= os.getenv("JAEGER_AGENT_PORT", 6831)  # Not used in current setup
OTEL_EXPORTER_JAEGER_ENDPOINT= os.getenv("OTEL_EXPORTER_JAEGER_ENDPOINT", "http://jaeger-collector.tracing.svc.cluster.local:14268/api/traces")
OTEL_SERVICE_NAME= os.getenv("OTEL_SERVICE_NAME", "hand-gesture-api")
JAEGER_HOSTNAME= os.getenv("JAEGER_HOSTNAME", "hand-gesture-api")