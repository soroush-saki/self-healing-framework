"""
Service monitoring module.

Continuously monitors managed services, detects failures,
and triggers recovery procedures.
"""

import time
from typing import Any, Dict, Optional

from core.service import ManagedService, ServiceState
from core.detector import FaultDetector
from core.recovery import RecoveryOrchestrator
from utils.logger import get_logger


logger = get_logger(__name__)


class ServiceMonitor:
    """
    Monitors managed services and coordinates fault detection and recovery.

    This is the main orchestration layer that ties together monitoring,
    detection, and recovery components.
    """

    def __init__(self):
        self.services: Dict[str, ManagedService] = {}
        self.detector = FaultDetector()
        self.recovery = RecoveryOrchestrator()
        self.monitoring: bool = False

    # ------------------------------------------------------------------
    # Service lifecycle management
    # ------------------------------------------------------------------

    def register_service(self, service: ManagedService) -> None:
        """Register a service for monitoring."""
        self.services[service.name] = service
        logger.info(
            f"Registered service: '{service.name}'",
            metadata={"state": service.get_state().value},
        )

    def unregister_service(self, service_name: str) -> None:
        """Unregister a service (stops it first)."""
        if service_name in self.services:
            self.services[service_name].stop()
            del self.services[service_name]
            self.detector.clear_history(service_name)
            logger.info(f"Unregistered service: '{service_name}'")

    def start_service(self, service_name: str) -> bool:
        """Start a registered service. Returns True on success."""
        if service_name not in self.services:
            logger.error(f"start_service: '{service_name}' not found")
            return False
        try:
            self.services[service_name].start()
            logger.info(f"Started service: '{service_name}'")
            return True
        except Exception as exc:
            logger.error(
                f"Failed to start '{service_name}'", metadata={"error": str(exc)}
            )
            return False

    def stop_service(self, service_name: str) -> None:
        """Stop a registered service."""
        if service_name in self.services:
            self.services[service_name].stop()
            logger.info(f"Stopped service: '{service_name}'")

    # ------------------------------------------------------------------
    # Monitored execution
    # ------------------------------------------------------------------

    def execute_with_monitoring(
        self,
        service_name: str,
        max_failures: int = 5,
    ) -> Optional[Any]:
        """
        Execute a service operation with fault monitoring and recovery.

        Args:
            service_name:  Name of the service to execute.
            max_failures:  Maximum consecutive failures before giving up.

        Returns:
            Operation result, or None if all recovery attempts failed.
        """
        if service_name not in self.services:
            logger.error(f"execute_with_monitoring: '{service_name}' not found")
            return None

        service = self.services[service_name]
        consecutive_failures = 0

        while consecutive_failures < max_failures:
            try:
                result = service.execute()

                if consecutive_failures > 0:
                    logger.info(
                        f"'{service_name}' recovered after {consecutive_failures} failure(s)"
                    )
                consecutive_failures = 0
                return result

            except Exception as exc:
                consecutive_failures += 1
                logger.error(
                    f"'{service_name}' execution failed",
                    metadata={
                        "error": str(exc),
                        "consecutive_failures": consecutive_failures,
                    },
                )

                severity = self.detector.classify_error(exc, service_name)

                recovered = self.recovery.recover(
                    service=service,
                    error=exc,
                    severity=severity,
                    operation=service.execute,
                )

                if recovered:
                    logger.info(f"Recovery succeeded for '{service_name}'")
                    consecutive_failures = 0
                else:
                    logger.error(
                        f"Recovery failed for '{service_name}' "
                        f"(consecutive_failures={consecutive_failures})"
                    )
                    if consecutive_failures >= max_failures:
                        logger.critical(
                            f"Max failures ({max_failures}) reached for '{service_name}' — giving up"
                        )
                        service.set_state(ServiceState.STOPPED_WITH_ERROR)
                        return None

        return None

    def monitor_loop(
        self,
        service_name: str,
        interval: float = 5.0,
        duration: Optional[float] = None,
    ) -> None:
        """
        Continuously monitor a service in a loop.

        Args:
            service_name: Service to monitor.
            interval:     Seconds between executions.
            duration:     Total run time in seconds (None = run forever).
        """
        logger.info(
            f"Starting monitor loop for '{service_name}'",
            metadata={"interval": interval, "duration": duration},
        )

        start_time = time.time()
        self.monitoring = True

        while self.monitoring:
            if duration and (time.time() - start_time) >= duration:
                logger.info(f"Monitoring duration reached for '{service_name}'")
                break
            self.execute_with_monitoring(service_name)
            time.sleep(interval)

        logger.info(f"Monitor loop ended for '{service_name}'")

    def stop_monitoring(self) -> None:
        """Signal all monitor loops to stop."""
        self.monitoring = False
        logger.info("Monitoring stopped")

    # ------------------------------------------------------------------
    # Status / observability
    # ------------------------------------------------------------------

    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Return a status dict for one service."""
        if service_name not in self.services:
            return {"error": "Service not found"}

        service = self.services[service_name]
        return {
            "name": service_name,
            "state": service.get_state().value,
            "healthy": service.health_check(),
            "recent_failures": self.detector.get_failure_count(service_name),
            "metadata": service.get_metadata(),
        }

    def get_all_service_status(self) -> Dict[str, Dict]:
        """Return status dicts for all registered services."""
        return {name: self.get_service_status(name) for name in self.services}
