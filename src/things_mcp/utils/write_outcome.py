"""Preserve ambiguous write outcomes across public-tool and fallback boundaries."""

from typing import Any, Dict, Optional


def uncertain_write(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a terminal public error for an ambiguous operation, else None.

    Callers must return this before another dispatch, fallback, or success
    wrapper. Preserve operation metadata and diagnostic text without requiring
    clients to parse human-readable error strings to determine retry safety.
    """
    if not (
        result.get("outcome_uncertain")
        or result.get("error_code") == "OUTCOME_UNCERTAIN"
        or result.get("error") == "OUTCOME_UNCERTAIN"
    ):
        return None
    return {
        **result,
        "success": False,
        "error": "OUTCOME_UNCERTAIN",
        "error_code": "OUTCOME_UNCERTAIN",
        "outcome_uncertain": True,
        "retry_safe": False,
        "message": result.get("message")
        or "The write may have applied; inspect Things before retrying.",
        "details": result.get("details") or result.get("error"),
    }
