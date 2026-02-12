"""
Main entry point for the Self-Healing Framework.

Runs five demonstration scenarios that progressively exercise
transient, recoverable, critical, and mixed failure patterns.
"""

import sys
import time

from core.monitor import ServiceMonitor
from core.health import HealthReporter
from services.sample_service import (
    StableService,
    TransientFailureService,
    RecoverableFailureService,
    CriticalFailureService,
    IntermittentService,
)
from utils.logger import get_logger


logger = get_logger(__name__)

DIVIDER = "=" * 70


# ======================================================================
# Individual demo scenarios
# ======================================================================

def demo_basic_monitoring() -> None:
    """Demo 1 — stable service, no failures."""
    print(f"\n{DIVIDER}")
    print("DEMO 1: Basic Service Monitoring (Stable Service)")
    print(f"{DIVIDER}\n")

    monitor = ServiceMonitor()
    reporter = HealthReporter()

    svc = StableService("BasicService")
    monitor.register_service(svc)
    monitor.start_service("BasicService")

    for _ in range(3):
        result = monitor.execute_with_monitoring("BasicService")
        print(f"  ✓  {result}")
        time.sleep(0.5)

    report = reporter.generate_report(monitor.get_all_service_status())
    print("\n" + reporter.format_report_text(report))
    monitor.stop_service("BasicService")


def demo_transient_failures() -> None:
    """Demo 2 — 30% failure rate; expects retry strategy."""
    print(f"\n{DIVIDER}")
    print("DEMO 2: Transient Failure Recovery  (Retry Strategy)")
    print(f"{DIVIDER}\n")

    monitor = ServiceMonitor()
    reporter = HealthReporter()

    svc = TransientFailureService("TransientService", failure_rate=0.3)
    monitor.register_service(svc)
    monitor.start_service("TransientService")

    print("  Service has a 30% failure rate — watch automatic retries...\n")

    for _ in range(5):
        result = monitor.execute_with_monitoring("TransientService")
        if result:
            print(f"  ✓  {result}")
        time.sleep(0.3)

    report = reporter.generate_report(monitor.get_all_service_status())
    print("\n" + reporter.format_report_text(report))
    monitor.stop_service("TransientService")


def demo_recoverable_failures() -> None:
    """Demo 3 — state corruption every 3 ops; expects restart strategy."""
    print(f"\n{DIVIDER}")
    print("DEMO 3: Recoverable Failure Recovery  (Restart Strategy)")
    print(f"{DIVIDER}\n")

    monitor = ServiceMonitor()
    reporter = HealthReporter()

    svc = RecoverableFailureService("RecoverableService", corruption_threshold=3)
    monitor.register_service(svc)
    monitor.start_service("RecoverableService")

    print("  State corrupts after every 3 operations — watch auto-restart...\n")

    for _ in range(8):
        result = monitor.execute_with_monitoring("RecoverableService")
        if result:
            print(f"  ✓  {result}")
        time.sleep(0.3)

    report = reporter.generate_report(monitor.get_all_service_status())
    print("\n" + reporter.format_report_text(report))
    monitor.stop_service("RecoverableService")


def demo_critical_failures() -> None:
    """Demo 4 — fatal error at execution 5; expects fallback strategy."""
    print(f"\n{DIVIDER}")
    print("DEMO 4: Critical Failure Handling  (Fallback → Degraded Mode)")
    print(f"{DIVIDER}\n")

    monitor = ServiceMonitor()
    reporter = HealthReporter()

    svc = CriticalFailureService("CriticalService", failure_at=5)
    monitor.register_service(svc)
    monitor.start_service("CriticalService")

    print("  Service will hit a critical failure at execution #5...\n")

    for _ in range(8):
        result = monitor.execute_with_monitoring("CriticalService")
        if result:
            print(f"  ✓  {result}")
        time.sleep(0.3)

    report = reporter.generate_report(monitor.get_all_service_status())
    print("\n" + reporter.format_report_text(report))
    monitor.stop_service("CriticalService")


def demo_multi_service() -> None:
    """Demo 5 — four services with mixed failure patterns."""
    print(f"\n{DIVIDER}")
    print("DEMO 5: Multi-Service Monitoring  (Mixed Failure Patterns)")
    print(f"{DIVIDER}\n")

    monitor = ServiceMonitor()
    reporter = HealthReporter()

    services = [
        StableService("Stable-1"),
        TransientFailureService("Transient-1", failure_rate=0.2),
        RecoverableFailureService("Recoverable-1", corruption_threshold=4),
        IntermittentService("Intermittent-1"),
    ]

    for svc in services:
        monitor.register_service(svc)
        monitor.start_service(svc.name)

    print("  Running 4 services for 10 iterations...\n")

    for iteration in range(1, 11):
        print(f"  --- Iteration {iteration} ---")
        for svc in services:
            result = monitor.execute_with_monitoring(svc.name)
            if result:
                print(f"    {svc.name}: {str(result)[:60]}")
        time.sleep(0.2)

    report = reporter.generate_report(monitor.get_all_service_status())
    print("\n" + reporter.format_report_text(report))

    for svc in services:
        monitor.stop_service(svc.name)


# ======================================================================
# Entry point
# ======================================================================

def main() -> None:
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║       SELF-HEALING SOFTWARE FRAMEWORK  —  DEMONSTRATION           ║
║                                                                   ║
║  Autonomous fault detection, classification, and recovery.        ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)

    demos = [
        demo_basic_monitoring,
        demo_transient_failures,
        demo_recoverable_failures,
        demo_critical_failures,
        demo_multi_service,
    ]

    for demo in demos:
        try:
            demo()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nDemonstration interrupted.")
            sys.exit(0)
        except Exception as exc:
            logger.error(f"Demo raised an unexpected exception: {exc}")

    print(f"\n{DIVIDER}")
    print("All demonstrations completed successfully.")
    print(f"{DIVIDER}\n")


if __name__ == "__main__":
    main()
