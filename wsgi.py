"""
Gunicorn WSGI entry point (alternative).
Canonical production command: gunicorn app:app
"""
from app import app  # noqa: F401

__all__ = ["app"]
