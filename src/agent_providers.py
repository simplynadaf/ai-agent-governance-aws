"""
Per-agent TracerProvider factory so each sub-agent's spans export under its OWN
resource identity (resource.agent.id), not just a span-level attribute.

WHY THIS EXISTS
---------------
Traccia's `init()` builds ONE OTLP/file resource whose `agent.id` is the value passed
at init time (here: "loan-prescreen"). Every exported span carries THAT resource,
because both exporters read the resource from `span.tracer._provider` and the OTel
resource is bound to the provider when the span/tracer is created.

`runtime_config.run_identity(agent_id=...)` only changes the SPAN-LEVEL `agent.id`
attribute (via the AgentEnrichmentProcessor). It cannot change the immutable
per-provider resource. Result on the Governance Hub: all three specialists
(intake / credit-risk / policy) register as agents but every trace is filed under
the orchestrator's resource identity, so the specialists show "no traces".

THE FIX
-------
Create a lightweight per-agent `TracerProvider` whose resource carries that agent's
`agent.id` / `agent.name`, and REUSE the fully-configured processor instances that
`init()` already attached to the main provider (enrichment chain + the OTel batch
export processors that ship to the OTLP endpoint and the file). Then swap the global
tracer provider for the duration of each specialist call so `@observe` uses it.

Specialist calls here are sequential and fully nested, so swapping the global
provider around each call is safe (no interleaving). On exit the orchestrator's
provider is restored.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Dict, Optional

import traccia
from traccia.tracer.provider import TracerProvider


# Cache one provider per agent id so we do not rebuild (and re-register exporters) on
# every call. All per-agent providers SHARE the same processor instances as the main
# provider, so spans flow through the identical enrichment + export pipeline.
_PROVIDERS: Dict[str, TracerProvider] = {}


def _clone_provider_with_identity(
    base: TracerProvider, agent_id: str, agent_name: str
) -> TracerProvider:
    """Build a provider identical to `base` but with a resource carrying this agent's id.

    Reuses `base`'s processor instances (both Traccia enrichment processors and the
    OTel export processors) so the per-agent spans reach the SAME OTLP endpoint / file
    exporter that init() configured. Only the resource identity differs.
    """
    # Start from the base resource dict so service.name, tenant.id, project.id, env,
    # compliance, etc. are preserved; only override the agent identity.
    resource = dict(getattr(base, "resource", {}) or {})
    resource["agent.id"] = agent_id
    resource["agent.name"] = agent_name

    prov = TracerProvider(resource=resource)

    # Carry over the sampler so head-sampling behaves the same.
    if getattr(base, "sampler", None) is not None:
        try:
            prov.set_sampler(base.sampler)
        except Exception:
            pass

    # Reuse the OTel export processors (BatchSpanProcessor -> OTLP endpoint, file, etc.)
    # These are what actually ship spans off-box, so the per-agent provider must feed
    # the same ones. add_span_processor routes OTel processors to the OTel provider.
    for proc in list(getattr(base, "_export_processors", []) or []):
        try:
            prov.add_span_processor(proc)
        except Exception:
            pass

    # Reuse the Traccia enrichment processors (agent enricher, guardrail detector,
    # governance enrichment, redaction, cost) so per-agent spans get identical
    # enrichment. These are added to the enrichment list, not the OTel provider.
    for proc in list(getattr(base, "_enrichment_processors", []) or []):
        try:
            prov.add_span_processor(proc)
        except Exception:
            pass

    return prov


def _get_agent_provider(agent_id: str, agent_name: str) -> TracerProvider:
    prov = _PROVIDERS.get(agent_id)
    if prov is None:
        base = traccia.get_tracer_provider()
        prov = _clone_provider_with_identity(base, agent_id, agent_name)
        _PROVIDERS[agent_id] = prov
    return prov


@contextmanager
def agent_identity_provider(*, agent_id: str, agent_name: str, new_trace: bool = True):
    """Run a nested block under a provider whose RESOURCE identity is this agent.

    Swaps the global tracer provider so any @observe/span spans created inside export
    with resource.agent.id == agent_id, and sets run-scoped identity so the span-level
    attributes agree.

    new_trace=True (default) ALSO detaches the current OpenTelemetry context for the
    duration of the block, so the specialist's @observe(as_type="agent") span starts as a
    NEW ROOT SPAN -> its own trace. This is what makes each specialist show up with its
    OWN traces on the Governance Hub: the Hub lists traces by their root/owning agent, so
    a specialist that only ever appears as a CHILD span of the orchestrator's trace has no
    trace of its own. Starting a fresh trace per specialist call fixes that.

    Restores the previous provider, identity, and OTel context on exit.
    """
    from traccia import runtime_config
    from opentelemetry import context as otel_context

    base = traccia.get_tracer_provider()
    prov = _get_agent_provider(agent_id, agent_name)

    # Detach current span context so the specialist span becomes a new root trace.
    ctx_token = None
    if new_trace:
        ctx_token = otel_context.attach(otel_context.Context())

    traccia.set_tracer_provider(prov)
    # Keep span-level identity consistent with the resource identity.
    with runtime_config.run_identity(agent_id=agent_id, agent_name=agent_name):
        try:
            yield prov
        finally:
            traccia.set_tracer_provider(base)
            if ctx_token is not None:
                otel_context.detach(ctx_token)


def flush_agent_providers(timeout: float = 6.0) -> None:
    """Force-flush every per-agent provider (they share exporters, but flush anyway)."""
    for prov in _PROVIDERS.values():
        try:
            prov.force_flush(timeout=timeout)
        except Exception:
            pass
