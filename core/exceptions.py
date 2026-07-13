"""
Global exception handler producing the SDD §16.19 error envelope:

    {
      "success": false,
      "code": "VALIDATION_ERROR",
      "message": "Validation failed.",
      "errors": [...],
      "timestamp": "2026-07-02T10:15:00Z"
    }
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.views import exception_handler

CODE_MAP = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
}


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django 500 (logged, generic message)

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message, errors = str(detail["detail"]), []
    else:
        message, errors = "Validation failed.", detail

    response.data = {
        "success": False,
        "code": CODE_MAP.get(response.status_code, "ERROR"),
        "message": message,
        "errors": errors,
        "timestamp": timezone.now().isoformat(),
    }
    return response
