"""Request logging — one line per request, so Render's Logs tab shows
what's actually happening (method, path, status, duration, user) instead
of only the business-logic logs individual views add explicitly."""

import logging
import time

logger = logging.getLogger("request")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - started) * 1000
        user = getattr(request, "user", None)
        user_label = user.email if getattr(user, "is_authenticated", False) else "anon"
        logger.info(
            "%s %s -> %s (%.1fms) user=%s",
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
            user_label,
        )
        return response
