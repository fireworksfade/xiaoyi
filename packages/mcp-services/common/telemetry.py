"""OpenTelemetry instrumentation setup for MCP services."""

import logging
import os
from functools import wraps

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


def setup_telemetry(service_name: str = "xiaoyi-mcp"):
    """Configure OpenTelemetry tracing for MCP service.

    Args:
        service_name: Service name for traces

    Environment variables:
        OTEL_SDK_DISABLED: Set to "true" to disable telemetry
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (default: http://localhost:4318)
    """
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        logger.info("OpenTelemetry disabled via OTEL_SDK_DISABLED")
        return

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

    logger.info(
        f"OpenTelemetry configured: service={service_name}, endpoint={otlp_endpoint}"
    )


def trace_tool(tool_name: str):
    """Decorator to trace MCP tool calls.

    Args:
        tool_name: Name of the tool being traced

    Example:
        @trace_tool("diagnose_device")
        async def diagnose_device(device_id: str) -> dict:
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                f"mcp.tool.{tool_name}",
                attributes={"mcp.tool.name": tool_name},
            ) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("mcp.tool.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("mcp.tool.success", False)
                    span.set_attribute("mcp.tool.error", str(e))
                    raise
        return wrapper
    return decorator
