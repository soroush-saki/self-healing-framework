"""
Sample services for demonstration and testing.

Five concrete ManagedService implementations, each exhibiting a distinct
failure pattern to exercise different recovery strategies in the framework.
"""

import random
import time
from typing import Any

from core.service import ManagedService, ServiceState
from core.errors import (
    NetworkTimeoutError,
    StateCorruptionError,
    CriticalError,
)


# ======================================================================
# 1. Stable service — never fails
# ======================================================================

class StableService(ManagedService):
    """A service that runs reliably without failures."""

    def __init__(self, name: str = "StableService"):
        super().__init__(name)
        self.execution_count: int = 0

    def start(self) -> None:
        self.set_state(ServiceState.RUNNING)
        self.execution_count = 0
        self.metadata["started_at"] = time.time()

    def stop(self) -> None:
        self.set_state(ServiceState.STOPPED)
        self.metadata["stopped_at"] = time.time()

    def execute(self) -> Any:
        if self.state != ServiceState.RUNNING:
            raise RuntimeError("Service is not running")
        self.execution_count += 1
        self.metadata["last_execution"] = time.time()
        return f"Execution #{self.execution_count} completed successfully"


# ======================================================================
# 2. Transient-failure service — random network timeouts
# ======================================================================

class TransientFailureService(ManagedService):
    """
    Occasionally raises NetworkTimeoutError to trigger retry recovery.

    Args:
        failure_rate: Probability [0, 1] of failure on each execute() call.
    """

    def __init__(self, name: str = "TransientFailureService", failure_rate: float = 0.3):
        super().__init__(name)
        self.failure_rate = failure_rate
        self.execution_count: int = 0
        self.successful_count: int = 0
        self.failed_count: int = 0

    def start(self) -> None:
        self.set_state(ServiceState.RUNNING)
        self.execution_count = 0
        self.successful_count = 0
        self.failed_count = 0
        self.metadata["started_at"] = time.time()

    def stop(self) -> None:
        self.set_state(ServiceState.STOPPED)
        self.metadata["stopped_at"] = time.time()

    def execute(self) -> Any:
        if self.state != ServiceState.RUNNING:
            raise RuntimeError("Service is not running")

        self.execution_count += 1

        if random.random() < self.failure_rate:
            self.failed_count += 1
            self.metadata["last_failure"] = time.time()
            raise NetworkTimeoutError(
                f"Network timeout on execution #{self.execution_count}",
                metadata={"execution": self.execution_count},
            )

        self.successful_count += 1
        self.metadata["last_execution"] = time.time()
        return (
            f"Execution #{self.execution_count} completed "
            f"(success rate: {self.successful_count}/{self.execution_count})"
        )


# ======================================================================
# 3. Recoverable-failure service — periodic state corruption
# ======================================================================

class RecoverableFailureService(ManagedService):
    """
    Raises StateCorruptionError after *corruption_threshold* operations,
    triggering the restart recovery strategy.

    Args:
        corruption_threshold: Operations allowed before state corrupts.
    """

    def __init__(
        self, name: str = "RecoverableFailureService", corruption_threshold: int = 5
    ):
        super().__init__(name)
        self.corruption_threshold = corruption_threshold
        self.execution_count: int = 0
        self.ops_since_restart: int = 0

    def start(self) -> None:
        self.set_state(ServiceState.RUNNING)
        self.ops_since_restart = 0
        self.metadata["started_at"] = time.time()
        self.metadata["restart_count"] = self.metadata.get("restart_count", 0) + 1

    def stop(self) -> None:
        self.set_state(ServiceState.STOPPED)
        self.metadata["stopped_at"] = time.time()

    def execute(self) -> Any:
        if self.state != ServiceState.RUNNING:
            raise RuntimeError("Service is not running")

        self.execution_count += 1
        self.ops_since_restart += 1

        if self.ops_since_restart >= self.corruption_threshold:
            self.metadata["last_corruption"] = time.time()
            raise StateCorruptionError(
                f"State corrupted after {self.ops_since_restart} operations",
                metadata={"operations": self.ops_since_restart},
            )

        self.metadata["last_execution"] = time.time()
        return (
            f"Execution #{self.execution_count} "
            f"(ops since restart: {self.ops_since_restart})"
        )


# ======================================================================
# 4. Critical-failure service — fatal error after N executions
# ======================================================================

class CriticalFailureService(ManagedService):
    """
    Raises CriticalError after *failure_at* executions, triggering
    the fallback strategy and DEGRADED mode.

    Args:
        failure_at: Execution number on which the critical failure fires.
    """

    def __init__(self, name: str = "CriticalFailureService", failure_at: int = 10):
        super().__init__(name)
        self.failure_at = failure_at
        self.execution_count: int = 0

    def start(self) -> None:
        self.set_state(ServiceState.RUNNING)
        self.execution_count = 0
        self.metadata["started_at"] = time.time()

    def stop(self) -> None:
        self.set_state(ServiceState.STOPPED)
        self.metadata["stopped_at"] = time.time()

    def execute(self) -> Any:
        if self.state == ServiceState.DEGRADED:
            return "Running in DEGRADED mode — limited functionality available"

        if self.state != ServiceState.RUNNING:
            raise RuntimeError("Service is not running")

        self.execution_count += 1

        if self.execution_count >= self.failure_at:
            self.metadata["critical_failure_time"] = time.time()
            raise CriticalError(
                f"Critical system failure at execution #{self.execution_count}",
                metadata={"execution": self.execution_count},
            )

        self.metadata["last_execution"] = time.time()
        return f"Execution #{self.execution_count} of {self.failure_at}"


# ======================================================================
# 5. Intermittent service — mixed random failure types
# ======================================================================

class IntermittentService(ManagedService):
    """
    Randomly mixes success, transient errors, recoverable errors,
    and (rarely) critical errors.  Good for testing the full
    classification and recovery pipeline end-to-end.
    """

    TRANSIENT_PROB = 0.15   # 15 %
    RECOVERABLE_PROB = 0.10 # 10 %
    CRITICAL_PROB = 0.02    # 2 %
    # Success: remaining ~73 %

    def __init__(self, name: str = "IntermittentService"):
        super().__init__(name)
        self.execution_count: int = 0

    def start(self) -> None:
        self.set_state(ServiceState.RUNNING)
        self.execution_count = 0
        self.metadata["started_at"] = time.time()

    def stop(self) -> None:
        self.set_state(ServiceState.STOPPED)
        self.metadata["stopped_at"] = time.time()

    def execute(self) -> Any:
        if self.state != ServiceState.RUNNING:
            raise RuntimeError("Service is not running")

        self.execution_count += 1
        rand = random.random()

        if rand < self.CRITICAL_PROB:
            raise CriticalError("Random critical failure")

        if rand < self.CRITICAL_PROB + self.RECOVERABLE_PROB:
            raise StateCorruptionError("Random state corruption")

        if rand < self.CRITICAL_PROB + self.RECOVERABLE_PROB + self.TRANSIENT_PROB:
            raise NetworkTimeoutError("Random network timeout")

        self.metadata["last_execution"] = time.time()
        return f"Execution #{self.execution_count} completed"
