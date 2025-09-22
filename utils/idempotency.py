# utils/idempotency.py
import functools
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status

from utils.responses import ErrorResponses

def idempotency_key(timeout: int = 60):
    """
    Decorator to enforce idempotency using Django cache (Redis).
    timeout: key expiration in seconds
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def _wrapped_view(view, request, *args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            if not key:
                return Response(
                    {"detail": "Idempotency-Key header is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cache_key = f"idempotency:{key}"
            if cache.get(cache_key):
                return Response(
                    ErrorResponses.IDEMPOTENCY,
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            cache.set(cache_key, "locked", timeout=timeout)

            response = view_func(view, request, *args, **kwargs)

            return response

        return _wrapped_view
    return decorator
