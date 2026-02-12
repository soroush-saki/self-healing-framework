"""
Base service interface for managed services.

Defines the contract that all managed services must implement
to be compatible with the self-healing framework.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict


class ServiceState(Enum):
    """Possible states for a managed service."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"              # Running with reduced functionality
    FAILING = "failing"
    STOPPED_WITH_ERROR = "stopped_with_error"


class ManagedService(ABC):
    """
    Abstract base class for services managed by the framework.

    All services must implement start(), stop(), and execute() methods.
    The framework will monitor execution and apply recovery strategies on failure.
    """

    def __init__(self, name: str):
        self.name = name
        self.state = ServiceState.STOPPED
        self.metadata: Dict[str, Any] = {}

    @abstractmethod
    def start(self) -> None:
        """
        Initialize and start the service.

        Raises:
            ServiceError: If service cannot be started.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Gracefully stop the service and clean up resources."""
        pass

    @abstractmethod
    def execute(self) -> Any:
        """
        Execute the main service operation.

        This method is called repeatedly by the monitoring layer.

        Returns:
            Result of the operation.

        Raises:
            ServiceError: On execution failure.
        """
        pass

    def get_state(self) -> ServiceState:
        """Get current service state."""
        return self.state

    def set_state(self, state: ServiceState) -> None:
        """Set service state."""
        self.state = state

    def get_metadata(self) -> Dict[str, Any]:
        """Get service metadata."""
        return self.metadata.copy()

    def health_check(self) -> bool:
        """
        Perform a health check on the service.

        Override this method for custom health checks.

        Returns:
            True if service is healthy, False otherwise.
        """
        return self.state in [ServiceState.RUNNING, ServiceState.DEGRADED]
