"""
Health reporting and status dashboard.

Provides a consolidated view of system health across all monitored services.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List

from core.service import ServiceState
from utils.logger import get_logger


logger = get_logger(__name__)


class SystemHealth(Enum):
    """Overall system health status."""
    HEALTHY = "healthy"    # All services running normally
    DEGRADED = "degraded"  # Some services degraded but operational
    CRITICAL = "critical"  # One or more services have failed


class HealthReporter:
    """
    Generates health reports for monitored services.

    Aggregates per-service status information into a system-wide view
    including alerts, summary metrics, and an overall health signal.
    """

    def __init__(self):
        self.last_report_time: datetime = datetime.utcnow()

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(self, service_statuses: Dict[str, Dict]) -> Dict:
        """
        Build a comprehensive health report.

        Args:
            service_statuses: Mapping returned by ServiceMonitor.get_all_service_status().

        Returns:
            Report dict with system_health, summary, alerts, and per-service details.
        """
        report_time = datetime.utcnow()

        total = len(service_statuses)
        healthy_count = sum(1 for s in service_statuses.values() if s.get("healthy"))
        degraded_count = sum(
            1 for s in service_statuses.values()
            if s.get("state") == ServiceState.DEGRADED.value
        )
        failed_count = sum(
            1 for s in service_statuses.values()
            if s.get("state") in (
                ServiceState.FAILING.value,
                ServiceState.STOPPED_WITH_ERROR.value,
            )
        )

        system_health = self._determine_system_health(
            total, healthy_count, degraded_count, failed_count
        )

        report = {
            "timestamp": report_time.isoformat(),
            "system_health": system_health.value,
            "summary": {
                "total_services": total,
                "healthy": healthy_count,
                "degraded": degraded_count,
                "failed": failed_count,
                "health_percentage": (healthy_count / total * 100) if total > 0 else 0.0,
            },
            "services": service_statuses,
            "alerts": self._generate_alerts(service_statuses),
        }

        self.last_report_time = report_time
        return report

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_report_text(self, report: Dict) -> str:
        """Render a health report as human-readable text."""
        lines: List[str] = []
        sep = "=" * 60

        lines += [
            sep,
            "SYSTEM HEALTH REPORT",
            sep,
            f"Timestamp:     {report['timestamp']}",
            f"System Health: {report['system_health'].upper()}",
            "",
        ]

        s = report["summary"]
        lines += [
            "SUMMARY:",
            f"  Total Services : {s['total_services']}",
            f"  Healthy        : {s['healthy']}",
            f"  Degraded       : {s['degraded']}",
            f"  Failed         : {s['failed']}",
            f"  Health         : {s['health_percentage']:.1f}%",
            "",
        ]

        if report["alerts"]:
            lines.append("ALERTS:")
            for alert in report["alerts"]:
                lines.append(f"  [{alert['severity'].upper()}] {alert['message']}")
            lines.append("")

        lines.append("SERVICES:")
        for name, status in report["services"].items():
            icon = "✓" if status.get("healthy") else "✗"
            state = status.get("state", "unknown")
            failures = status.get("recent_failures", 0)
            lines.append(f"  {icon} {name}: {state}  (recent failures: {failures})")

        lines.append(sep)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _determine_system_health(
        self, total: int, healthy: int, degraded: int, failed: int
    ) -> SystemHealth:
        if total == 0:
            return SystemHealth.HEALTHY
        if failed > 0:
            return SystemHealth.CRITICAL
        if degraded > 0 or healthy < total:
            return SystemHealth.DEGRADED
        return SystemHealth.HEALTHY

    def _generate_alerts(self, service_statuses: Dict[str, Dict]) -> List[Dict]:
        alerts: List[Dict] = []

        for name, status in service_statuses.items():
            state = status.get("state", "")

            if state in (ServiceState.FAILING.value, ServiceState.STOPPED_WITH_ERROR.value):
                alerts.append({
                    "severity": "critical",
                    "service": name,
                    "message": f"Service '{name}' has failed (state={state})",
                    "state": state,
                })
            elif state == ServiceState.DEGRADED.value:
                alerts.append({
                    "severity": "warning",
                    "service": name,
                    "message": f"Service '{name}' is running in DEGRADED mode",
                    "state": state,
                })

            failure_count = status.get("recent_failures", 0)
            if failure_count >= 5:
                alerts.append({
                    "severity": "warning",
                    "service": name,
                    "message": f"Service '{name}' has {failure_count} recent failures",
                    "failure_count": failure_count,
                })

        return alerts
