"""
Unit tests for the self-healing framework.

Run with:
    pytest tests/ -v
    pytest tests/ --cov=core --cov=services --cov-report=term-missing
"""

import pytest

from core.errors import (
    ErrorSeverity,
    TransientError,
    RecoverableError,
    CriticalError,
    NetworkTimeoutError,
    StateCorruptionError,
)
from core.service import ServiceState
from core.detector import FaultDetector
from core.recovery import (
    RetryStrategy,
    RestartStrategy,
    FallbackStrategy,
    RecoveryOrchestrator,
)
from core.monitor import ServiceMonitor
from core.health import HealthReporter, SystemHealth
from services.sample_service import StableService, TransientFailureService


# ======================================================================
# Error Classification
# ======================================================================

class TestErrorClassification:
    """Tests for error severity hierarchy."""

    def test_transient_error_severity(self):
        assert TransientError("t").severity == ErrorSeverity.TRANSIENT

    def test_recoverable_error_severity(self):
        assert RecoverableError("r").severity == ErrorSeverity.RECOVERABLE

    def test_critical_error_severity(self):
        assert CriticalError("c").severity == ErrorSeverity.CRITICAL

    def test_error_metadata_attached(self):
        meta = {"key": "value", "count": 42}
        error = TransientError("test", metadata=meta)
        assert error.metadata == meta

    def test_error_str_includes_severity(self):
        error = TransientError("boom")
        assert "TRANSIENT" in str(error)


# ======================================================================
# Fault Detection
# ======================================================================

class TestFaultDetector:
    """Tests for FaultDetector classification and pattern logic."""

    def test_classify_network_timeout_as_transient(self):
        detector = FaultDetector()
        severity = detector.classify_error(NetworkTimeoutError("timeout"), "svc")
        assert severity == ErrorSeverity.TRANSIENT

    def test_classify_state_corruption_as_recoverable(self):
        detector = FaultDetector()
        severity = detector.classify_error(StateCorruptionError("corrupted"), "svc")
        assert severity == ErrorSeverity.RECOVERABLE

    def test_classify_critical_error(self):
        detector = FaultDetector()
        severity = detector.classify_error(CriticalError("fatal"), "svc")
        assert severity == ErrorSeverity.CRITICAL

    def test_classify_builtin_timeout_as_transient(self):
        detector = FaultDetector()
        assert detector.classify_error(TimeoutError("to"), "svc") == ErrorSeverity.TRANSIENT

    def test_classify_value_error_as_recoverable(self):
        detector = FaultDetector()
        assert detector.classify_error(ValueError("bad"), "svc") == ErrorSeverity.RECOVERABLE

    def test_failure_count_tracking(self):
        detector = FaultDetector()
        for _ in range(5):
            detector.classify_error(TransientError("e"), "svc1")
        assert detector.get_failure_count("svc1") == 5
        assert detector.get_failure_count("svc2") == 0

    def test_severity_escalation_transient_to_recoverable(self):
        detector = FaultDetector()
        for _ in range(6):
            detector.classify_error(TransientError("repeated"), "svc")
        # 7th error should be escalated
        severity = detector.classify_error(TransientError("still failing"), "svc")
        assert severity == ErrorSeverity.RECOVERABLE

    def test_clear_history(self):
        detector = FaultDetector()
        detector.classify_error(TransientError("e"), "svc")
        assert detector.get_failure_count("svc") == 1
        detector.clear_history("svc")
        assert detector.get_failure_count("svc") == 0

    def test_clear_history_does_not_affect_other_services(self):
        detector = FaultDetector()
        detector.classify_error(TransientError("e"), "svc1")
        detector.classify_error(TransientError("e"), "svc2")
        detector.clear_history("svc1")
        assert detector.get_failure_count("svc1") == 0
        assert detector.get_failure_count("svc2") == 1


# ======================================================================
# Recovery Strategies
# ======================================================================

class TestRetryStrategy:
    """Tests for RetryStrategy."""

    def test_succeeds_on_third_attempt(self):
        strategy = RetryStrategy(max_attempts=3, base_delay=0.01)
        service = StableService("s")
        service.start()

        attempts = [0]

        def op():
            attempts[0] += 1
            if attempts[0] < 3:
                raise TransientError("not yet")

        assert strategy.recover(service, TransientError("t"), op) is True
        assert attempts[0] == 3

    def test_returns_false_when_all_attempts_fail(self):
        strategy = RetryStrategy(max_attempts=3, base_delay=0.01)
        service = StableService("s")
        service.start()

        def always_fail():
            raise TransientError("always")

        assert strategy.recover(service, TransientError("t"), always_fail) is False

    def test_returns_false_without_operation(self):
        strategy = RetryStrategy()
        service = StableService("s")
        service.start()
        assert strategy.recover(service, TransientError("t"), None) is False


class TestRestartStrategy:
    """Tests for RestartStrategy."""

    def test_service_running_after_restart(self):
        strategy = RestartStrategy(cleanup_state=True, restart_delay=0.01)
        service = StableService("s")
        service.start()

        assert strategy.recover(service, RecoverableError("r")) is True
        assert service.get_state() == ServiceState.RUNNING

    def test_metadata_cleared_when_cleanup_true(self):
        strategy = RestartStrategy(cleanup_state=True, restart_delay=0.01)
        service = StableService("s")
        service.start()
        service.metadata["sentinel"] = "present"

        strategy.recover(service, RecoverableError("r"))
        assert "sentinel" not in service.metadata

    def test_metadata_preserved_when_cleanup_false(self):
        strategy = RestartStrategy(cleanup_state=False, restart_delay=0.01)
        service = StableService("s")
        service.start()
        service.metadata["sentinel"] = "present"

        strategy.recover(service, RecoverableError("r"))
        # metadata is cleared by stop(), then start() adds started_at;
        # without cleanup the framework preserves user keys added *before* stop.
        # Because StableService.stop() doesn't touch metadata beyond setting state,
        # the sentinel should still be there.
        assert service.metadata.get("sentinel") == "present"


class TestFallbackStrategy:
    """Tests for FallbackStrategy."""

    def test_service_set_to_degraded(self):
        strategy = FallbackStrategy()
        service = StableService("s")
        service.start()

        assert strategy.recover(service, CriticalError("c")) is True
        assert service.get_state() == ServiceState.DEGRADED

    def test_fallback_hook_called(self):
        called = [False]

        def hook(svc):
            called[0] = True

        strategy = FallbackStrategy(fallback_hook=hook)
        service = StableService("s")
        service.start()
        strategy.recover(service, CriticalError("c"))
        assert called[0] is True


class TestRecoveryOrchestrator:
    """Tests for RecoveryOrchestrator decision logic."""

    def test_transient_error_retries_then_succeeds(self):
        orchestrator = RecoveryOrchestrator()
        service = StableService("s")
        service.start()

        attempts = [0]

        def op():
            attempts[0] += 1
            if attempts[0] == 1:
                raise TransientError("once")

        assert orchestrator.recover(service, TransientError("t"), ErrorSeverity.TRANSIENT, op) is True

    def test_recoverable_error_restarts_service(self):
        orchestrator = RecoveryOrchestrator()
        service = StableService("s")
        service.start()

        result = orchestrator.recover(service, RecoverableError("r"), ErrorSeverity.RECOVERABLE)
        assert result is True
        assert service.get_state() == ServiceState.RUNNING

    def test_critical_error_falls_back(self):
        orchestrator = RecoveryOrchestrator()
        service = StableService("s")
        service.start()

        result = orchestrator.recover(service, CriticalError("c"), ErrorSeverity.CRITICAL)
        assert result is True
        assert service.get_state() == ServiceState.DEGRADED


# ======================================================================
# Service Monitor
# ======================================================================

class TestServiceMonitor:
    """Tests for ServiceMonitor orchestration."""

    def test_register_service(self):
        monitor = ServiceMonitor()
        service = StableService("svc")
        monitor.register_service(service)
        assert "svc" in monitor.services

    def test_start_service(self):
        monitor = ServiceMonitor()
        service = StableService("svc")
        monitor.register_service(service)
        assert monitor.start_service("svc") is True
        assert service.get_state() == ServiceState.RUNNING

    def test_start_unknown_service_returns_false(self):
        monitor = ServiceMonitor()
        assert monitor.start_service("ghost") is False

    def test_execute_returns_result(self):
        monitor = ServiceMonitor()
        service = StableService("svc")
        monitor.register_service(service)
        monitor.start_service("svc")

        result = monitor.execute_with_monitoring("svc")
        assert result is not None
        assert "successfully" in result

    def test_execute_unknown_service_returns_none(self):
        monitor = ServiceMonitor()
        assert monitor.execute_with_monitoring("ghost") is None

    def test_recovery_on_transient_failure(self):
        monitor = ServiceMonitor()
        # failure_rate=0 → always succeeds after first call in recovery
        service = TransientFailureService("svc", failure_rate=0.0)
        monitor.register_service(service)
        monitor.start_service("svc")

        result = monitor.execute_with_monitoring("svc")
        assert result is not None

    def test_get_service_status(self):
        monitor = ServiceMonitor()
        service = StableService("svc")
        monitor.register_service(service)
        monitor.start_service("svc")

        status = monitor.get_service_status("svc")
        assert status["name"] == "svc"
        assert status["state"] == ServiceState.RUNNING.value
        assert status["healthy"] is True

    def test_get_all_service_status(self):
        monitor = ServiceMonitor()
        for i in range(3):
            svc = StableService(f"svc{i}")
            monitor.register_service(svc)
            monitor.start_service(f"svc{i}")

        statuses = monitor.get_all_service_status()
        assert len(statuses) == 3

    def test_unregister_service(self):
        monitor = ServiceMonitor()
        service = StableService("svc")
        monitor.register_service(service)
        monitor.unregister_service("svc")
        assert "svc" not in monitor.services

    def test_stop_service(self):
        monitor = ServiceMonitor()
        service = StableService("svc")
        monitor.register_service(service)
        monitor.start_service("svc")
        monitor.stop_service("svc")
        assert service.get_state() == ServiceState.STOPPED


# ======================================================================
# Health Reporter
# ======================================================================

class TestHealthReporter:
    """Tests for HealthReporter report generation."""

    def _running_status(self, **kwargs):
        base = {"state": ServiceState.RUNNING.value, "healthy": True, "recent_failures": 0}
        base.update(kwargs)
        return base

    def test_all_healthy(self):
        reporter = HealthReporter()
        statuses = {
            "s1": self._running_status(),
            "s2": self._running_status(),
        }
        report = reporter.generate_report(statuses)
        assert report["system_health"] == SystemHealth.HEALTHY.value
        assert report["summary"]["health_percentage"] == 100.0

    def test_degraded_service_makes_system_degraded(self):
        reporter = HealthReporter()
        statuses = {
            "s1": self._running_status(),
            "s2": {"state": ServiceState.DEGRADED.value, "healthy": True, "recent_failures": 2},
        }
        report = reporter.generate_report(statuses)
        assert report["system_health"] == SystemHealth.DEGRADED.value
        assert report["summary"]["degraded"] == 1

    def test_failed_service_makes_system_critical(self):
        reporter = HealthReporter()
        statuses = {
            "s1": {"state": ServiceState.STOPPING_WITH_ERROR if hasattr(ServiceState, 'STOPPING_WITH_ERROR') else ServiceState.STOPPED_WITH_ERROR.value, "healthy": False, "recent_failures": 10},
        }
        # Ensure the state value is the raw string
        statuses["s1"]["state"] = ServiceState.STOPPED_WITH_ERROR.value
        report = reporter.generate_report(statuses)
        assert report["system_health"] == SystemHealth.CRITICAL.value

    def test_critical_alert_generated_for_failed_service(self):
        reporter = HealthReporter()
        statuses = {
            "bad": {
                "state": ServiceState.STOPPED_WITH_ERROR.value,
                "healthy": False,
                "recent_failures": 8,
            }
        }
        report = reporter.generate_report(statuses)
        critical_alerts = [a for a in report["alerts"] if a["severity"] == "critical"]
        assert len(critical_alerts) >= 1

    def test_warning_alert_for_high_failure_count(self):
        reporter = HealthReporter()
        statuses = {
            "flaky": self._running_status(recent_failures=6),
        }
        report = reporter.generate_report(statuses)
        warning_alerts = [a for a in report["alerts"] if a["severity"] == "warning"]
        assert len(warning_alerts) >= 1

    def test_empty_system_is_healthy(self):
        reporter = HealthReporter()
        report = reporter.generate_report({})
        assert report["system_health"] == SystemHealth.HEALTHY.value
        assert report["summary"]["total_services"] == 0

    def test_format_report_text_contains_key_fields(self):
        reporter = HealthReporter()
        statuses = {"s1": self._running_status()}
        report = reporter.generate_report(statuses)
        text = reporter.format_report_text(report)

        assert "SYSTEM HEALTH REPORT" in text
        assert "System Health" in text
        assert "SUMMARY" in text
        assert "SERVICES" in text


# ======================================================================
# Sample Services
# ======================================================================

class TestSampleServices:
    """Tests for sample service implementations."""

    def test_stable_service_lifecycle(self):
        svc = StableService("t")
        svc.start()
        assert svc.get_state() == ServiceState.RUNNING

        result = svc.execute()
        assert result is not None
        assert svc.execution_count == 1

        svc.stop()
        assert svc.get_state() == ServiceState.STOPPED

    def test_transient_service_raises_on_guaranteed_failure(self):
        svc = TransientFailureService("t", failure_rate=1.0)
        svc.start()
        with pytest.raises(NetworkTimeoutError):
            svc.execute()
        assert svc.failed_count == 1

    def test_transient_service_succeeds_on_zero_failure_rate(self):
        svc = TransientFailureService("t", failure_rate=0.0)
        svc.start()
        result = svc.execute()
        assert result is not None
        assert svc.successful_count == 1

    def test_health_check_running_is_healthy(self):
        svc = StableService("t")
        svc.set_state(ServiceState.RUNNING)
        assert svc.health_check() is True

    def test_health_check_degraded_is_healthy(self):
        svc = StableService("t")
        svc.set_state(ServiceState.DEGRADED)
        assert svc.health_check() is True

    def test_health_check_stopped_is_unhealthy(self):
        svc = StableService("t")
        svc.set_state(ServiceState.STOPPED)
        assert svc.health_check() is False

    def test_health_check_failed_is_unhealthy(self):
        svc = StableService("t")
        svc.set_state(ServiceState.STOPPED_WITH_ERROR)
        assert svc.health_check() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
