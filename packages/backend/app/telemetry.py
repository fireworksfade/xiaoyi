"""OpenTelemetry instrumentation setup for backend."""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def setup_telemetry(app):
    """Configure OpenTelemetry tracing for FastAPI application.

    Args:
        app: FastAPI application instance

    Environment variables:
        OTEL_SDK_DISABLED: Set to "true" to disable telemetry
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (default: http://localhost:4318)
        OTEL_SERVICE_NAME: Service name for traces (default: xiaoyi-backend)
    """
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        logger.info("OpenTelemetry disabled via OTEL_SDK_DISABLED")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "xiaoyi-backend")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    # Create resource with service name
    resource = Resource.create({"service.name": service_name})

    # Configure tracer provider
    provider = TracerProvider(resource=resource)

    # Add OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Manual ASGI instrumentation instead of FastAPI auto-instrumentation
    # to avoid AttributeError with _IncludedRouter
    # Note: excluded_urls must be a compiled ExcludeList, not a string
    from opentelemetry.util.http import ExcludeList

    excluded = ExcludeList(["/ready", "/health", "/docs", "/openapi.json"])

    app.add_middleware(OpenTelemetryMiddleware, excluded_urls=excluded)

    logger.info(f"OpenTelemetry configured: service={service_name}, endpoint={otlp_endpoint}")
