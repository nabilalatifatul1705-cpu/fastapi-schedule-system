"""Lapisan service. Berisi exception bersama agar tidak ada circular import."""
from typing import Any, Dict, Optional


class ServiceError(Exception):
    """Error bisnis dasar; dipetakan ke respons HTTP di app/main.py."""

    status_code = 400

    def __init__(self, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload or {}


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class CapacityError(ServiceError):
    status_code = 422


class InvalidScheduleError(ServiceError):
    status_code = 422
