from api.constant.config import (
    JAEGER_COLLECTOR_HOST, 
    JAEGER_AGENT_PORT, 
    JAEGER_HOSTNAME, 
    OTEL_SERVICE_NAME
)
# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.sdk.resources import Resource
import logging

logger = logging.getLogger(__name__)

# Configure OpenTelemetry
def configure_tracing():
    try:
        print(f"[TRACER] Starting tracing configuration...")
        print(f"[TRACER] Service: {OTEL_SERVICE_NAME}")
        print(f"[TRACER] Collector: {JAEGER_COLLECTOR_HOST}:4317")
        
        # Create a resource with service information
        resource = Resource.create({
            "service.name": OTEL_SERVICE_NAME,
            "service.version": "1.0.0",
            "service.instance.id": JAEGER_HOSTNAME,
        })
        print(f"[TRACER] Resource created: {resource.attributes}")
        
        # Set up the tracer provider
        trace.set_tracer_provider(TracerProvider(resource=resource))
        tracer = trace.get_tracer(__name__)
        print(f"[TRACER] TracerProvider set: {type(trace.get_tracer_provider())}")
        
        # Use the collector's OTLP gRPC endpoint (port 4317)
        # where to export the traces to (the collector)
        endpoint = f"{JAEGER_COLLECTOR_HOST}:4317"
        print(f"[TRACER] Creating OTLP exporter for: {endpoint}")
        
        otlp_exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=True, # Set to True if not using TLS
        ) 
        print(f"[TRACER] OTLP exporter created: {type(otlp_exporter)}")
        
        # Add the exporter to the tracer provider with error handling
        span_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=2048,
            schedule_delay_millis=5000,
            max_export_batch_size=512,
            export_timeout_millis=30000,
        )
        trace.get_tracer_provider().add_span_processor(span_processor)
        print(f"[TRACER] Span processor added: {type(span_processor)}")
        
        logger.info(f"Tracing configured successfully for service: {OTEL_SERVICE_NAME}")
        logger.info(f"Sending traces to: {JAEGER_COLLECTOR_HOST}:4317")
        print(f"[TRACER] Configuration complete - traces will be sent to Jaeger")
        
        return tracer
        
    except Exception as e:
        logger.error(f"Failed to configure tracing: {str(e)}")
        print(f"[TRACER] ERROR: Failed to configure tracing: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return a no-op tracer if configuration fails
        return trace.NoOpTracer()
