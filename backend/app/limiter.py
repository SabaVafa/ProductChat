"""Shared rate limiter. Public endpoints (esp. /chat, which costs an LLM call)
get per-IP limits to curb abuse and runaway cost."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
