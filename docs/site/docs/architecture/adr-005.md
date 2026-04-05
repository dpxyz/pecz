# ADR-005: Observability Boundaries

**Status:** ACCEPTED (Retrospectively documented)  
**Date:** 2026-04-03  
**Phase:** 3 (Observability) - Delivered 2026-03-27  
**Decision Date:** 2026-03-27  
**Author:** Forward Team  
**Supersedes:** n/a  
**Superseded by:** n/a

## Context

Phase 3 (Observability) required a clear separation between SAFETY and OBSERVABILITY concerns to prevent observability failures from blocking trading operations. The system needed to handle monitoring, reporting, and alerting without interfering with the critical execution path.

## Decision

We establish a **strict boundary** between SAFETY and OBSERVABILITY domains:

### Boundary Rules

| Domain | Responsibility | Failure Impact | Examples |
|--------|---------------|----------------|----------|
| **SAFETY** | Trading-critical checks | BLOCKS trading | Circuit breaker, position limits, balance checks |
| **OBSERVABILITY** | Monitoring & reporting | Never blocks | Health checks, logs, reports, metrics |

### Implementation

```
┌─────────────────────────────────────────────────────────────┐
│                      SAFETY DOMAIN                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Circuit      │  │ Position     │  │ Balance      │        │
│  │ Breaker      │  │ Risk Engine  │  │ Projection   │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                             │
│  Failure → BLOCK trading → Event store → Recovery         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ (triggers, never blocks)
┌─────────────────────────────────────────────────────────────┐
│                   OBSERVABILITY DOMAIN                       │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Health       │  │ Logger       │  │ Report       │        │
│  │ Checker      │  │ Service      │  │ Service      │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                             │
│  Failure → WARN only → Never affects SAFETY                 │
└─────────────────────────────────────────────────────────────┘
```

## Consequences

### Positive
- **Trading reliability**: OBSERVABILITY failures never halt trading
- **Clear operational model**: Teams know which failures require immediate action
- **Testable separation**: G3 Recovery tests verify boundary adherence
- **Simplified incident response**: SAFETY alerts = stop trading; OBSERVABILITY alerts = investigate

### Negative
- **Duplication**: Some checks exist in both domains (e.g., health vs. mandatory circuit breaker)
- **Monitoring blind spots**: If OBSERVABILITY fails, we may not detect issues until SAFETY triggers

## Boundary Enforcement

### Code Patterns

```javascript
// SAFETY check - can block
circuitBreaker.recordSafetyFailure('memory_critical', details);
if (circuitBreaker.isOpen()) {
  blockTrading(); // HARD STOP
}

// OBSERVABILITY check - never blocks
health.checkMemory()
  .then(result => {
    if (result.status === 'CRITICAL') {
      alertEngine.warn('Memory high'); // Notification only
    }
  })
  .catch(err => {
    logger.error('Health check failed', err); // Log only
    // NEVER blocks trading
  });
```

### Module Responsibility Matrix

| Module | Domain | Blocks Trading? | File |
|--------|--------|-----------------|------|
| `circuit_breaker.js` | SAFETY | YES | `src/circuit_breaker.js` |
| `risk_engine.js` | SAFETY | YES | `src/risk_engine.js` |
| `health_checker.js` | OBSERVABILITY | NO | `src/health_checker.js` |
| `logger.js` | OBSERVABILITY | NO | `src/logger.js` |
| `report_service.js` | OBSERVABILITY | NO | `src/report_service.js` |

## Validation

Acceptance Gate G3 (Recovery Scenarios) validates this boundary:
- G3.1: Circuit breaker opens (SAFETY) and recovers correctly
- G3.2: State projection reset (OBSERVABILITY) with no zombie state
- G3.5: Recovery is observable (OBSERVABILITY never affects SAFETY logic)

## References

- [Phase 3 Deliverables](phases.md#phase-3-observability-complete)
- [G3 Acceptance Tests](../tests/acceptance_g3_recovery_scenarios.test.js)
- `src/health.js` - Health service with explicit domain classification
- `src/circuit_breaker.js` - SAFETY boundary enforcer

---

*This ADR was documented retrospectively on 2026-04-03 after implementation
was completed in Phase 3 (completed 2026-03-27). The architecture has been
operational since that date.*
