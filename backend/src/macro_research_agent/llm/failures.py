"""Safe provider failure classification; never expose response text or credentials."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    message: str
    retryable: bool


def classify_provider_error(error: httpx.HTTPError) -> ProviderFailure:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 402:
            return ProviderFailure(
                "provider_payment_required",
                "AI provider reports insufficient credit/payment required. Restore API credit "
                "before retrying; existing progress and budgets are preserved.",
                False,
            )
        if status in {401, 403}:
            return ProviderFailure(
                "provider_authentication_failed",
                "AI provider rejected credentials/access. Check the configured key and permissions "
                "before retrying; existing progress is preserved.",
                False,
            )
        if status == 429:
            return ProviderFailure(
                "provider_rate_limited",
                "AI provider rate limit reached. Wait before retrying within the remaining budget.",
                True,
            )
        if status >= 500:
            return ProviderFailure(
                "provider_server_error",
                "AI provider service failed. Retry within remaining budget when it recovers.",
                True,
            )
        return ProviderFailure(
            "provider_request_rejected",
            "AI provider rejected the request. Check endpoint/model configuration before retrying.",
            False,
        )
    if isinstance(error, httpx.TimeoutException):
        return ProviderFailure(
            "provider_timeout",
            "AI provider call timed out. Attempt retained; retry within remaining budget.",
            True,
        )
    return ProviderFailure(
        "provider_connection_failed",
        "AI provider connection failed. Check connection; retry within remaining budget.",
        True,
    )
