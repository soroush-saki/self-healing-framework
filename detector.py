"""
Fault detection and classification module.

Analyzes exceptions and service behavior to classify errors by severity
and determine appropriate recovery strategies.
"""

from core.errors import (
    ServiceError,
    ErrorSeverity,
    TransientError,
    RecoverableError,
    CriticalError,
)
from utils.logger import get_logger


logger = get_logger(__name__)


class FaultDetector:
    """
    Detects and classifies faults in managed services.

    Uses exception type hierarchy and error patterns to determine
    the severity of failures and guide recovery strategy selection.
    """

    def __init__(self):
        self.error_history: list[tuple[str, Exception]] = []
        self.max_history: int = 100

    def classify_error(self, error: Exception, service_name: str) -> ErrorSeverity:
        """
        Classify an error by severity.

        Args:
            error: The exception that occurred.
            service_name: Name of the service where error occurred.

        Returns:
            ErrorSeverity indicating how to handle the error.
        """
        self._record_error(service_name, error)

        # If already a ServiceError, use its built-in severity
        if isinstance(error, ServiceError):
            severity = error.severity
        else:
            severity = self._classify_by_type(error)

        # Pattern-based escalation (repeated failures)
        severity = self._adjust_for_patterns(service_name, severity)

        logger.info(
            f"Classified error in '{service_name}'",
            metadata={
                "service": service_name,
                "error_type": type(error).__name__,
                "severity": severity.value,
                "message": str(error),
            },
        )
        return severity

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_by_type(self, error: Exception) -> ErrorSeverity:
        """Classify error based on exception type hierarchy."""
        if isinstance(error, TransientError):
            return ErrorSeverity.TRANSIENT
        if isinstance(error, CriticalError):
            return ErrorSeverity.CRITICAL
        if isinstance(error, RecoverableError):
            return ErrorSeverity.RECOVERABLE

        # Map built-in exceptions
        if isinstance(error, (TimeoutError, ConnectionError)):
            return ErrorSeverity.TRANSIENT
        if isinstance(error, (ValueError, KeyError, AttributeError)):
            return ErrorSeverity.RECOVERABLE
        if isinstance(error, (MemoryError, SystemError)):
            return ErrorSeverity.CRITICAL

        # Default: treat unknown errors as recoverable
        return ErrorSeverity.RECOVERABLE

    def _adjust_for_patterns(
        self, service_name: str, base_severity: ErrorSeverity
    ) -> ErrorSeverity:
        """
        Escalate severity when repeated failures are detected.

        A service that keeps throwing 'transient' errors is no longer
        experiencing a transient condition – it needs stronger intervention.
        """
        recent_failures = sum(
            1 for svc, _ in self.error_history[-10:] if svc == service_name
        )

        if recent_failures >= 5 and base_severity == ErrorSeverity.TRANSIENT:
            logger.warning(
                f"Escalating severity for '{service_name}': TRANSIENT → RECOVERABLE",
                metadata={"recent_failures": recent_failures},
            )
            return ErrorSeverity.RECOVERABLE

        if recent_failures >= 8 and base_severity == ErrorSeverity.RECOVERABLE:
            logger.error(
                f"Escalating severity for '{service_name}': RECOVERABLE → CRITICAL",
                metadata={"recent_failures": recent_failures},
            )
            return ErrorSeverity.CRITICAL

        return base_severity

    def _record_error(self, service_name: str, error: Exception) -> None:
        """Record error in sliding-window history."""
        self.error_history.append((service_name, error))
        if len(self.error_history) > self.max_history:
            self.error_history = self.error_history[-self.max_history:]

    # ------------------------------------------------------------------
    # Public utilities
    # ------------------------------------------------------------------

    def get_failure_count(self, service_name: str, window: int = 10) -> int:
        """Return the number of recent failures for a service within *window*."""
        return sum(
            1 for svc, _ in self.error_history[-window:] if svc == service_name
        )

    def clear_history(self, service_name: str) -> None:
        """Clear error history for a specific service."""
        self.error_history = [
            (svc, err) for svc, err in self.error_history if svc != service_name
        ]
        logger.info(f"Cleared error history for '{service_name}'")
