"""
Error classification system for self-healing framework.

Defines a taxonomy of errors that can occur in managed services,
categorized by their recoverability and appropriate recovery strategies.
"""

from enum import Enum
from typing import Optional


class ErrorSeverity(Enum):
    """Severity levels for error classification."""
    TRANSIENT = "transient"      # Temporary, likely to resolve on retry
    RECOVERABLE = "recoverable"  # Requires intervention but recoverable
    CRITICAL = "critical"        # Non-recoverable, requires manual intervention


class ServiceError(Exception):
    """Base exception for all service errors."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.RECOVERABLE,
        metadata: Optional[dict] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.metadata = metadata or {}

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.message}"


class TransientError(ServiceError):
    """
    Errors that are temporary and likely to resolve on retry.
    Examples: network timeouts, temporary resource unavailability.
    """

    def __init__(self, message: str, metadata: Optional[dict] = None):
        super().__init__(message, ErrorSeverity.TRANSIENT, metadata)


class RecoverableError(ServiceError):
    """
    Errors that require intervention but can be recovered.
    Examples: configuration errors, dependency failures.
    """

    def __init__(self, message: str, metadata: Optional[dict] = None):
        super().__init__(message, ErrorSeverity.RECOVERABLE, metadata)


class CriticalError(ServiceError):
    """
    Non-recoverable errors requiring manual intervention.
    Examples: security violations, data corruption.
    """

    def __init__(self, message: str, metadata: Optional[dict] = None):
        super().__init__(message, ErrorSeverity.CRITICAL, metadata)


# --- Specific error types for common scenarios ---

class NetworkTimeoutError(TransientError):
    """Network request timeout."""
    pass


class ResourceUnavailableError(TransientError):
    """Required resource temporarily unavailable."""
    pass


class ConfigurationError(RecoverableError):
    """Invalid or missing configuration."""
    pass


class DependencyFailureError(RecoverableError):
    """External dependency is unavailable."""
    pass


class StateCorruptionError(RecoverableError):
    """Service state has become corrupted."""
    pass


class SecurityViolationError(CriticalError):
    """Security constraint violated."""
    pass


class DataCorruptionError(CriticalError):
    """Data integrity compromised."""
    pass
