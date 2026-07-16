"""OTel tracing bootstrap for PolySignal (Phoenix or any OTLP backend).

Activates only when OTEL_ENABLED=1 AND the opentelemetry packages are
importable — dev checkouts and CI never break on missing deps, and the
scanner behaves identically with tracing off. The primary bet is the data
plane, not the viewer (ADR L2): spans are plain OTel, the backend is
whatever OTEL_EXPORTER_OTLP_ENDPOINT points at, and the pinned semconv
versions ride on every resource so a future rename is an additive
migration, not a rewrite.

Environment:
    OTEL_ENABLED                  "1" to activate (default off)
    OTEL_SERVICE_NAME             logical service (e.g. polysignal-scanner)
    OTEL_EXPORTER_OTLP_ENDPOINT   base URL, default http://127.0.0.1:6006
                                  (/v1/traces is appended here)
"""

from __future__ import annotations

import os
from contextlib import contextmanager

# Pinned instrumentation contract (ADR L3): recorded on the resource of
# every span so rows remain self-describing across semconv upgrades.
OTEL_SEMCONV_PIN = "opentelemetry-semantic-conventions==0.64b0"
OPENINFERENCE_SEMCONV_PIN = "openinference-semantic-conventions==0.1.30"

_TRACER_PROVIDER = None


def setup_tracing(service_name: str | None = None):
    """Idempotent tracer-provider setup. Returns the provider or None."""
    global _TRACER_PROVIDER
    if _TRACER_PROVIDER is not None:
        return _TRACER_PROVIDER
    if os.getenv("OTEL_ENABLED", "0") != "1":
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return None

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:6006")
    resource = Resource.create(
        {
            "service.name": service_name
            or os.getenv("OTEL_SERVICE_NAME", "polysignal"),
            "semconv.pin.otel": OTEL_SEMCONV_PIN,
            "semconv.pin.openinference": OPENINFERENCE_SEMCONV_PIN,
            "deployment.environment": os.getenv("DEPLOY_ENV", "dgx"),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER = provider

    # LLM + graph-node spans (gen_ai.* attributes) via OpenInference, when
    # installed. Instruments langchain-core Runnables, which covers both
    # ChatOpenAI calls and LangGraph node execution.
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)
    except ImportError:
        pass
    return provider


@contextmanager
def cycle_span(name: str, **attributes):
    """Root/child span helper; a no-op context when tracing is inactive.

    Yields the span (or None), so callers may set result attributes after
    the wrapped work completes.
    """
    if _TRACER_PROVIDER is None:
        yield None
        return
    from opentelemetry import trace

    tracer = trace.get_tracer("polysignal")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span
