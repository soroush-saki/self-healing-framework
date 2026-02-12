"""
Recovery strategy implementation.

Defines different recovery strategies (retry, restart, fallback)
and orchestrates their application based on error severity.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from core.errors import ErrorSeverity
from core.service import ManagedService, ServiceState
from utils.logger import get_logger


logger = get_logger(__name__)


# ======================================================================
# Abstract base
# ======================================================================

class RecoveryStrategy(ABC):
    """Abstract base class for recovery strategies."""

    @abstractmethod
    def recover(
        self,
        service: ManagedService,
        error: Exception,
        operation: Optional[Callable] = None,
    ) -> bool:
        """
        Attempt to recover from an error.

        Args:
            service:   The service that encountered the error.
            error:     The exception that occurred.
            operation: Optional callable to retry (used by RetryStrategy).

        Returns:
            True if recovery succeeded, False otherwise.
        """
        pass


# ======================================================================
# Concrete strategies
# ======================================================================

class RetryStrategy(RecoveryStrategy):
    """
    Retry with exponential backoff.

    Best suited for transient errors (network timeouts, brief unavailability).
    Formula: delay = base_delay × 2^(attempt-2)  (no delay on first retry).
    """

    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay

    def recover(
        self,
        service: ManagedService,
        error: Exception,
        operation: Optional[Callable] = None,
    ) -> bool:
        if operation is None:
            logger.error("RetryStrategy requires an operation callable.")
            return False

        logger.info(
            f"RetryStrategy: starting for '{service.name}'",
            metadata={"max_attempts": self.max_attempts},
        )

        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                delay = self.base_delay * (2 ** (attempt - 2))
                logger.debug(
                    f"  Retry {attempt}/{self.max_attempts} — waiting {delay:.1f}s",
                    metadata={"service": service.name},
                )
                time.sleep(delay)

            try:
                operation()
                logger.info(
                    f"RetryStrategy: succeeded for '{service.name}'",
                    metadata={"attempt": attempt},
                )
                return True
            except Exception as exc:
                logger.warning(
                    f"  Attempt {attempt} failed for '{service.name}'",
                    metadata={"error": str(exc)},
                )

        logger.error(f"RetryStrategy: all attempts exhausted for '{service.name}'")
        return False


class RestartStrategy(RecoveryStrategy):
    """
    Stop and restart the service, optionally clearing its state.

    Best suited for recoverable errors where state has become inconsistent.
    """

    def __init__(self, cleanup_state: bool = True, restart_delay: float = 0.5):
        self.cleanup_state = cleanup_state
        self.restart_delay = restart_delay

    def recover(
        self,
        service: ManagedService,
        error: Exception,
        operation: Optional[Callable] = None,
    ) -> bool:
        logger.info(
            f"RestartStrategy: starting for '{service.name}'",
            metadata={"cleanup_state": self.cleanup_state},
        )

        try:
            service.stop()

            if self.cleanup_state:
                service.metadata.clear()
                logger.debug(f"  State cleared for '{service.name}'")

            time.sleep(self.restart_delay)
            service.start()

            if service.get_state() == ServiceState.RUNNING:
                logger.info(f"RestartStrategy: '{service.name}' is RUNNING again")
                return True

            logger.error(
                f"RestartStrategy: '{service.name}' not RUNNING after restart "
                f"(state={service.get_state().value})"
            )
            return False

        except Exception as exc:
            logger.error(
                f"RestartStrategy: restart failed for '{service.name}'",
                metadata={"error": str(exc)},
            )
            return False


class FallbackStrategy(RecoveryStrategy):
    """
    Degrade the service to limited-functionality (DEGRADED) mode.

    Used when full recovery is not possible but partial operation is
    preferable to complete unavailability.
    """

    def __init__(self, fallback_hook: Optional[Callable[[ManagedService], None]] = None):
        self.fallback_hook = fallback_hook

    def recover(
        self,
        service: ManagedService,
        error: Exception,
        operation: Optional[Callable] = None,
    ) -> bool:
        logger.info(f"FallbackStrategy: degrading '{service.name}' to DEGRADED mode")

        try:
            service.set_state(ServiceState.DEGRADED)

            if self.fallback_hook:
                self.fallback_hook(service)

            logger.info(
                f"FallbackStrategy: '{service.name}' is now in DEGRADED mode"
            )
            return True

        except Exception as exc:
            logger.error(
                f"FallbackStrategy: failed for '{service.name}'",
                metadata={"error": str(exc)},
            )
            return False


# ======================================================================
# Orchestrator
# ======================================================================

class RecoveryOrchestrator:
    """
    Selects and chains recovery strategies based on error severity.

    Decision logic:
      TRANSIENT   → Retry  → (if fails) Restart
      RECOVERABLE → Restart → (if fails) Fallback
      CRITICAL    → Fallback only (log critical alert)
    """

    def __init__(self):
        self.retry_strategy = RetryStrategy(max_attempts=3, base_delay=1.0)
        self.restart_strategy = RestartStrategy(cleanup_state=True)
        self.fallback_strategy = FallbackStrategy()

    def recover(
        self,
        service: ManagedService,
        error: Exception,
        severity: ErrorSeverity,
        operation: Optional[Callable] = None,
    ) -> bool:
        """
        Recover from *error* using the strategy appropriate for *severity*.

        Returns True if any recovery strategy succeeds.
        """
        logger.info(
            f"RecoveryOrchestrator: recovering '{service.name}'",
            metadata={"severity": severity.value, "error_type": type(error).__name__},
        )

        if severity == ErrorSeverity.TRANSIENT:
            if self.retry_strategy.recover(service, error, operation):
                return True
            logger.info(f"  Retry failed — escalating to Restart for '{service.name}'")
            return self.restart_strategy.recover(service, error)

        if severity == ErrorSeverity.RECOVERABLE:
            if self.restart_strategy.recover(service, error):
                return True
            logger.info(f"  Restart failed — escalating to Fallback for '{service.name}'")
            return self.fallback_strategy.recover(service, error)

        if severity == ErrorSeverity.CRITICAL:
            logger.critical(
                f"CRITICAL failure in '{service.name}' — applying Fallback only",
                metadata={"error": str(error)},
            )
            return self.fallback_strategy.recover(service, error)

        return False
