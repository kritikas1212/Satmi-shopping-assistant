from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from satmi_agent.config import settings


_tracing_initialized = False


def setup_tracing() -> None:
    global _tracing_initialized
    if _tracing_initialized:
        return
    if not settings.tracing_enabled:
        return

    resource = Resource.create(
        {
            SERVICE_NAME: settings.tracing_service_name,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.tracing_exporter.lower() == "otlp":
        exporter = OTLPSpanExporter(
            endpoint=settings.tracing_otlp_endpoint,
            timeout=settings.tracing_timeout_seconds,
        )
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracing_initialized = True


def get_tracer(name: str = "satmi_agent"):
    return trace.get_tracer(name)
