# Self-Healing Software Framework

> A lightweight, academically-oriented Python framework demonstrating autonomous fault detection, classification, and recovery in managed services.

---

## Motivation

Modern software systems operate under conditions of constant uncertainty: transient network failures, memory leaks, corrupted state, and cascading dependency errors. Traditional approaches respond to failures reactively — an operator receives an alert, diagnoses the root cause, and manually restarts or reconfigures the affected component. This model does not scale with system complexity.

**Self-healing systems** aim to automate this feedback loop. By continuously monitoring execution, classifying errors, and applying pre-defined recovery strategies, a self-healing framework can restore normal operation without human intervention — reducing mean time to recovery (MTTR) and improving overall availability.

This project implements core self-healing principles in a clean, modular Python framework. It is intended as an experimental engineering artefact, not a production system. The emphasis is on architectural clarity, separation of concerns, and demonstrating well-established patterns from the field of autonomic computing.

---

## System Architecture

The framework is organized into four layers, each with a single responsibility:

```
┌──────────────────────────────────────────────────────────┐
│              ORCHESTRATION  (monitor.py)                  │
│  Registers services, drives execution, coordinates        │
│  detection and recovery.                                  │
└───────────────────┬──────────────────────────────────────┘
                    │
       ┌────────────┴────────────┐
       │                         │
┌──────▼──────────┐   ┌──────────▼──────────┐
│  DETECTION       │   │  HEALTH REPORTING   │
│  (detector.py)   │   │  (health.py)        │
│                  │   │                     │
│  Classifies      │   │  Aggregates per-    │
│  exceptions by   │   │  service status;    │
│  severity and    │   │  generates alerts   │
│  detects error   │   │  and system-wide    │
│  patterns.       │   │  health signal.     │
└──────┬───────────┘   └─────────────────────┘
       │
┌──────▼──────────────────────────────────────┐
│  RECOVERY  (recovery.py)                    │
│                                             │
│  RetryStrategy      — exponential backoff   │
│  RestartStrategy    — stop / clean / start  │
│  FallbackStrategy   — degrade gracefully    │
│  RecoveryOrchestrator — selects & chains    │
└──────────────────────────────────────────────┘
```

---

## How Fault Detection Works

Errors are classified by a three-tier severity model:

| Severity | Characteristics | Example |
|---|---|---|
| **TRANSIENT** | Temporary; likely to resolve on retry | `NetworkTimeoutError` |
| **RECOVERABLE** | Requires intervention; service can be restarted | `StateCorruptionError` |
| **CRITICAL** | Non-recoverable without manual action | `DataCorruptionError` |

The `FaultDetector` applies two classification steps:

1. **Type-based classification** — maps exception types to severity levels via the error hierarchy.
2. **Pattern-based escalation** — if a service accumulates ≥5 recent failures the severity is escalated (TRANSIENT → RECOVERABLE; RECOVERABLE → CRITICAL) to prevent infinite retry loops.

---

## Recovery Strategy Explanation

Recovery strategies are implemented using the **Strategy Pattern**, making them independently testable and swappable.

### RetryStrategy
Retries the failed operation up to *N* times with **exponential backoff**:

```
delay(attempt) = base_delay × 2^(attempt − 2)
```

Typical timeline: immediate → 1 s → 2 s → 4 s

### RestartStrategy
Stops the service, optionally clears its metadata (state cleanup), and restarts it. Suitable for state-corruption errors where the service logic itself is correct but internal state has become inconsistent.

### FallbackStrategy
Transitions the service to `DEGRADED` state where it can continue offering limited functionality. This is the last resort before declaring a service permanently failed. An optional hook lets implementors customize degraded-mode behavior.

### RecoveryOrchestrator
Chains strategies based on severity:

```
TRANSIENT   → Retry → (if fails) Restart
RECOVERABLE → Restart → (if fails) Fallback
CRITICAL    → Fallback only
```

---

## Example Workflow

```
1.  Service raises NetworkTimeoutError during execute()

2.  ServiceMonitor catches the exception.

3.  FaultDetector.classify_error()
      └─ Type check: NetworkTimeoutError → TRANSIENT
      └─ Pattern check: < 5 recent failures → no escalation
      └─ Returns: ErrorSeverity.TRANSIENT

4.  RecoveryOrchestrator.recover(..., severity=TRANSIENT)
      └─ Delegates to RetryStrategy

5.  RetryStrategy
      Attempt 1 (immediate): fails
      Attempt 2 (after 1 s) : succeeds ✓

6.  ServiceMonitor resets consecutive-failure counter.
    Service continues normal execution.

7.  HealthReporter records service as HEALTHY.
```

---

## Project Structure

```
self_healing_framework/
│
├── core/
│   ├── errors.py       # Error taxonomy and exception hierarchy
│   ├── service.py      # ManagedService abstract interface
│   ├── detector.py     # Fault detection and classification
│   ├── recovery.py     # Recovery strategies + orchestrator
│   ├── monitor.py      # Service monitoring (main orchestration)
│   └── health.py       # Health reporting and alerting
│
├── services/
│   └── sample_service.py  # Five demo services with distinct failure modes
│
├── utils/
│   └── logger.py       # Structured logging with metadata support
│
├── tests/
│   └── test_framework.py  # Comprehensive unit tests (pytest)
│
├── main.py             # Demonstration entry point
├── requirements.txt
└── README.md
```

---

## Installation

```bash
# Python 3.8+ required
git clone https://github.com/yourusername/self-healing-framework.git
cd self-healing-framework
pip install -r requirements.txt
```

---

## Running the Demonstrations

```bash
python main.py
```

Five scenarios are demonstrated in sequence:

| Demo | Service | Failure Pattern | Recovery |
|---|---|---|---|
| 1 | `StableService` | None | — |
| 2 | `TransientFailureService` | 30% random timeouts | Retry |
| 3 | `RecoverableFailureService` | State corrupts every 3 ops | Restart |
| 4 | `CriticalFailureService` | Fatal error at execution #5 | Fallback |
| 5 | Mixed (4 services) | All patterns combined | All strategies |

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=core --cov=services --cov-report=term-missing
```

Expected output: **30+ passing tests** covering all components.

---

## Design Principles

| Principle | Application |
|---|---|
| Separation of Concerns | Detection, recovery, monitoring, and health reporting are independent modules. |
| Strategy Pattern | Recovery algorithms are interchangeable without modifying the orchestrator. |
| Template Method Pattern | `ManagedService` defines lifecycle; subclasses implement the operations. |
| Dependency Inversion | `ServiceMonitor` depends on the `ManagedService` abstraction, not concrete classes. |
| Open / Closed Principle | New services and recovery strategies can be added without modifying existing code. |

---

## Future Research Directions

This framework intentionally focuses on a single node. Natural extensions include:

1. **Circuit Breaker Pattern** — prevent cascade failures when a dependency is consistently unavailable.
2. **Distributed Fault Detection** — consensus-based health checking across nodes (Gossip protocol, Phi Accrual detector).
3. **Predictive Recovery** — train a classifier on historical error sequences to predict failures before they occur.
4. **Formal Verification** — use model-checking tools (TLA+, Alloy) to prove liveness and safety properties of the recovery protocols.
5. **Reinforcement Learning** — let an agent learn optimal recovery strategy selection by observing MTTR and resource cost.
6. **Checkpointing & Rollback** — snapshot service state periodically so recovery can restore a known-good snapshot rather than restarting from scratch.

---

## Related Work

- **IBM MAPE-K Loop** (Kephart & Chess, 2003) — foundational autonomic computing reference architecture.
- **Netflix Hystrix** — circuit-breaker and fallback library for JVM microservices.
- **Kubernetes Pod Lifecycle** — liveness / readiness probes, restart policies.
- **Erlang/OTP Supervisor Trees** — hierarchical "let it crash" fault isolation.
- **AWS SDK Retry Policies** — production exponential-backoff implementation.

---

## License

MIT License — see `LICENSE` for details.

---

## Author

Developed as part of a graduate scholarship application, demonstrating software architecture design, fault-tolerance engineering, and clean-code principles in Python.
