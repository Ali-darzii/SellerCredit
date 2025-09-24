import time
import logging

from functools import wraps
from django.db import IntegrityError
from django.db.transaction import TransactionManagementError

logger = logging.getLogger("django")

def retry_on_conflict(max_retries=3, delay=0.1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            error = []
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (IntegrityError, TransactionManagementError) as e:
                    error.append(e)
                    if attempt == max_retries - 1:
                        logger.critical(f"ERROR AT `{func.__qualname__}` \n {error}")
                        raise
                    time.sleep(delay * (2 ** attempt))
            return None
        return wrapper
    return decorator