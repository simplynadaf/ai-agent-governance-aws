"""
Configuration + robustness helpers for the loan-decision crew.

Production systems read config from the environment (with safe defaults), fail fast with a
clear message when prerequisites are missing, log structured events, and retry transient
model errors. This module centralizes all of that.
"""
from __future__ import annotations

import src._env  # noqa: F401  -- ensures .env is loaded before env reads
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")

# Versions stamped onto every decision's evidence (traceability — EU AI Act Art. 12).
POLICY_VERSION = "loan-policy-v1.2.0"
MODEL_VERSION = "amazon.nova-pro-v1:0"


@dataclass(frozen=True)
class Settings:
    region: str
    model_id: str
    temperature: float
    max_tokens: int
    session_id: str
    max_retries: int
    retry_base_delay_s: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            region=os.environ.get("AWS_REGION", "us-east-1"),
            model_id=os.environ.get("LOAN_MODEL_ID", "amazon.nova-pro-v1:0"),
            temperature=float(os.environ.get("LOAN_TEMPERATURE", "0.2")),
            max_tokens=int(os.environ.get("LOAN_MAX_TOKENS", "400")),
            session_id=os.environ.get("LOAN_SESSION_ID", "session-loan-demo"),
            max_retries=int(os.environ.get("LOAN_MAX_RETRIES", "3")),
            retry_base_delay_s=float(os.environ.get("LOAN_RETRY_BASE_DELAY_S", "0.8")),
        )


SETTINGS = Settings.from_env()


# --------------------------------------------------- quiet benign OTel shutdown warnings
# We call force_flush() explicitly at the end of each run, so all spans/metrics ARE
# delivered. OpenTelemetry then ALSO runs its own atexit shutdown, which logs harmless
# WARNINGs against the now-empty, already-shut-down exporters:
#   "Exporter already shutdown, ignoring batch" / "shutdown can only be called once"
# These are cosmetic double-shutdown notices (no telemetry is lost) but they clutter the
# demo output. Raise ONLY these OTel exporter loggers to ERROR so real errors still show.
# Override with OTEL_LOG_LEVEL if you want the raw warnings back.
if "OTEL_LOG_LEVEL" not in os.environ:
    for _otel_logger in (
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        "opentelemetry.exporter.otlp.proto.http.metric_exporter",
        "opentelemetry.exporter.otlp.proto.http._log_exporter",
        "opentelemetry.sdk.metrics._internal",
    ):
        logging.getLogger(_otel_logger).setLevel(logging.ERROR)


# ------------------------------------------------------------------ structured logging
def get_logger(name: str = "loan_crew") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s :: %(message)s", "%H:%M:%S"
        ))
        logger.addHandler(h)
        logger.setLevel(os.environ.get("LOAN_LOG_LEVEL", "INFO").upper())
        logger.propagate = False
    return logger


log = get_logger()


# ------------------------------------------------------------------ transient-error retry
# Bedrock throttling / transient errors surface as these (by class name, to avoid a hard
# botocore import here). Real production code retries with exponential backoff + jitter.
_TRANSIENT = (
    "ThrottlingException", "TooManyRequestsException", "ServiceUnavailable",
    "ModelTimeoutException", "InternalServerException", "ModelNotReadyException",
    "ConnectionError", "ReadTimeoutError", "EndpointConnectionError",
)


def is_transient(exc: BaseException) -> bool:
    name = exc.__class__.__name__
    if name in _TRANSIENT:
        return True
    # botocore ClientError carries the AWS error code in response["Error"]["Code"]
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
    return code in _TRANSIENT


def with_retry(fn: Callable[[], T], *, what: str, retries: int | None = None) -> T:
    """Run fn() with exponential backoff on transient errors. Non-transient errors re-raise."""
    retries = SETTINGS.max_retries if retries is None else retries
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - we re-raise non-transient below
            attempt += 1
            if attempt > retries or not is_transient(exc):
                log.error("%s failed (attempt %d, non-retryable): %s", what, attempt, exc)
                raise
            delay = SETTINGS.retry_base_delay_s * (2 ** (attempt - 1))
            log.warning("%s transient error (attempt %d/%d), retrying in %.1fs: %s",
                        what, attempt, retries, delay, exc)
            time.sleep(delay)


# ------------------------------------------------------------------ fail-fast preflight
class ConfigError(RuntimeError):
    """Raised when a prerequisite (AWS creds / model access) is missing."""


def preflight(check_bedrock: bool = True) -> None:
    """Validate prerequisites with a clear message BEFORE the crew runs."""
    try:
        import boto3  # noqa: F401
    except ImportError as e:
        raise ConfigError("boto3 is not installed. Run: pip install -r requirements.txt") from e

    if not check_bedrock:
        return
    try:
        import boto3
        sts = boto3.client("sts", region_name=SETTINGS.region)
        acct = sts.get_caller_identity()["Account"]
        log.info("AWS preflight OK: account=%s region=%s model=%s", acct, SETTINGS.region, SETTINGS.model_id)
    except Exception as e:  # noqa: BLE001
        raise ConfigError(
            f"AWS credentials/region not usable ({e}). Configure credentials and ensure "
            f"Nova Pro ({SETTINGS.model_id}) access is enabled in the Bedrock console for "
            f"region {SETTINGS.region}. See iam/bedrock-invoke-policy.json."
        ) from e
