from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance for API and credential endpoints.
limiter = Limiter(key_func=get_remote_address)
