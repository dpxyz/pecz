/**
 * Block 4.5: System Boundaries Integration Tests
 *
 * End-to-End Tests für SAFETY/OBSERVABILITY Boundary
 * Verifies: Health + CircuitBreaker + Events + Trading
 */

const test = require('node:test');
const assert = require('node:assert');

// Setup: Fresh modules for each test
let Health, CircuitBreaker, Logger, events;

function setup() {
  // Clear caches
  delete require.cache[require.resolve('../src/health.js')];
  delete require.cache[require.resolve('../src/circuit_breaker.js')];
  delete require.cache[require.resolve('../src/logger.js')];
  
  events = [];
  
  // Load modules
  Logger = require('../src/logger.js');
  CircuitBreaker = require('../src/circuit_breaker.js');
  Health = require('../src/health.js');
  
  // Reset state
  CircuitBreaker._reset();
  
  // Configure CircuitBreaker with event capture
  CircuitBreaker.configure({
    onStateChange: (eventType, data) => {
      events.push({ eventType, ...data, timestamp: Date.now() });
    }
  });
}

test.beforeEach(() => {
  setup();
});

test.afterEach(() => {
  events = [];
});

// ============================================================================
// Integration Tests
// ============================================================================

test('IT1: SAFETY failure → breaker OPEN → trading blocked', async () => {
  // Stelle sicher: Trading erlaubt
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), true);
  
  // Simuliere SAFETY Fehler via Health (falls möglich) oder direkt
  CircuitBreaker.recordSafetyFailure('event_store', { error: 'DB timeout' });
  
  // Verify: Breaker OPEN
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.state, 'OPEN');
  assert.strictEqual(status.isTradingAllowed, false);
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), false);
  
  // Verify: Event emitted
  assert.strictEqual(events.length, 1);
  assert.strictEqual(events[0].eventType, 'CIRCUIT_BREAKER_OPENED');
  assert.strictEqual(events[0].newState, 'OPEN');
});

test('IT2: OBSERVABILITY failure → WARN only → breaker stays CLOSED', async () => {
  // Initial: CLOSED
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED');
  
  // Mehrere OBSERVABILITY Fehler
  for (let i = 0; i < 5; i++) {
    CircuitBreaker.recordObservabilityFailure('discord_webhook');
    CircuitBreaker.recordObservabilityFailure('logger_fallback');
    CircuitBreaker.recordObservabilityFailure('report_service');
  }
  
  // Verify: Immer noch CLOSED
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.state, 'CLOSED');
  assert.strictEqual(status.isTradingAllowed, true);
  assert.strictEqual(status.failureCount, 0); // OBS zählt nicht
  
  // Verify: Keine State-Change Events
  assert.strictEqual(events.length, 0);
});

test('IT3: Manual reset path: OPEN → HALF_OPEN → CLOSED', async () => {
  // Schritt 1: OPEN erreichen
  CircuitBreaker.recordSafetyFailure('watchdog_tick');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
  assert.strictEqual(events.length, 1);
  
  // Schritt 2: attemptReset → HALF_OPEN
  const resetResult = CircuitBreaker.attemptReset();
  assert.strictEqual(resetResult, true);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN');
  assert.strictEqual(events.length, 2);
  assert.strictEqual(events[1].eventType, 'CIRCUIT_BREAKER_HALF_OPEN');
  
  // Schritt 3: confirmReset → CLOSED
  // Mock Health.getStatus() für diesen Test
  const originalGetStatus = Health.getStatus;
  Health.getStatus = () => ({ isPaused: false });
  
  const confirmResult = CircuitBreaker.confirmReset();
  
  // Restore
  Health.getStatus = originalGetStatus;
  
  assert.strictEqual(confirmResult, true);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED');
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), true);
  assert.strictEqual(events.length, 3);
  assert.strictEqual(events[2].eventType, 'CIRCUIT_BREAKER_CLOSED');
});

test('IT4: confirmReset() blocked if SAFETY still failing', async () => {
  // OPEN
  CircuitBreaker.recordSafetyFailure('risk_engine');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
  
  // HALF_OPEN
  CircuitBreaker.attemptReset();
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN');
  
  // Mock: SAFETY noch fehlerhaft
  const originalGetStatus = Health.getStatus;
  Health.getStatus = () => ({ isPaused: true, isMonitoring: true });
  
  const confirmResult = CircuitBreaker.confirmReset();
  
  // Restore
  Health.getStatus = originalGetStatus;
  
  assert.strictEqual(confirmResult, false);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN');
  
  // Kein CLOSED Event
  assert.strictEqual(events.filter(e => e.eventType === 'CIRCUIT_BREAKER_CLOSED').length, 0);
});

test('IT5: Mixed failures - SAFETY wins', async () => {
  // Zuerst OBSERVABILITY Fehler
  CircuitBreaker.recordObservabilityFailure('discord_webhook');
  CircuitBreaker.recordObservabilityFailure('logger_fallback');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED');
  
  // Dann SAFETY Fehler
  CircuitBreaker.recordSafetyFailure('reconcile_positions');
  
  // Ergebnis: OPEN
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), false);
});

test('IT6: Event chain complete', async () => {
  // Mock Health für diesen Test (isPaused = false = alle Checks OK)
  const originalGetStatus = Health.getStatus;
  Health.getStatus = () => ({ isPaused: false, isMonitoring: true });
  
  // Simuliere komplette Event-Kette
  
  // 1. SAFETY Fehler
  CircuitBreaker.recordSafetyFailure('event_store');
  
  // 2. Reset
  CircuitBreaker.attemptReset();
  
  // 3. Confirm
  CircuitBreaker.confirmReset();
  
  // Restore Health
  Health.getStatus = originalGetStatus;
  
  // Verify: Alle 3 Events vorhanden
  assert.strictEqual(events.length, 3);
  assert.strictEqual(events[0].eventType, 'CIRCUIT_BREAKER_OPENED');
  assert.strictEqual(events[0].newState, 'OPEN');
  assert.strictEqual(events[1].eventType, 'CIRCUIT_BREAKER_HALF_OPEN');
  assert.strictEqual(events[1].newState, 'HALF_OPEN');
  assert.strictEqual(events[2].eventType, 'CIRCUIT_BREAKER_CLOSED');
  assert.strictEqual(events[2].newState, 'CLOSED');
  
  // Verify: Zeitliche Reihenfolge (>= da gleiche ms möglich)
  assert.ok(events[1].timestamp >= events[0].timestamp);
  assert.ok(events[2].timestamp >= events[1].timestamp);
});

test('IT7: Documentation matches runtime behavior', async () => {
  // Verifiziere: doku/safety_boundary.md Regeln stimmen mit Runtime überein
  
  // Regel 1: SAFETY öffnet Breaker
  CircuitBreaker._reset();
  CircuitBreaker.recordSafetyFailure('event_store');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN', 
    'SAFETY boundary violation must open breaker per safety_boundary.md');
  
  // Regel 2: OBSERVABILITY öffnet NICHT
  CircuitBreaker._reset();
  CircuitBreaker.recordObservabilityFailure('discord_webhook');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED',
    'OBSERVABILITY failure must NOT open breaker per observability_boundary.md');
  
  // Regel 3: Manual reset required
  CircuitBreaker.recordSafetyFailure('watchdog_tick');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
  CircuitBreaker.attemptReset();
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN',
    'Manual reset via attemptReset() required per incident_response.md');
});

test('IT8: attemptReset() ignored if not OPEN', async () => {
  // Von CLOSED
  const r1 = CircuitBreaker.attemptReset();
  assert.strictEqual(r1, false);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED');
  
  // Von HALF_OPEN
  CircuitBreaker.recordSafetyFailure('event_store');
  CircuitBreaker.attemptReset();
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN');
  
  const r2 = CircuitBreaker.attemptReset();
  assert.strictEqual(r2, false);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN'); // Unchanged
});

test('IT9: confirmReset() ignored if not HALF_OPEN', async () => {
  // Von CLOSED
  const r1 = CircuitBreaker.confirmReset();
  assert.strictEqual(r1, false);
  
  // Von OPEN
  CircuitBreaker.recordSafetyFailure('event_store');
  const r2 = CircuitBreaker.confirmReset();
  assert.strictEqual(r2, false);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
});

test('IT10: Full end-to-end: SAFETY violation to recovery', async () => {
  // Komplette Story:
  
  // 1. System läuft normal
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), true);
  
  // 2. SAFETY Fehler tritt auf
  CircuitBreaker.recordSafetyFailure('event_store', { reason: 'Connection lost' });
  
  // 3. Trading gestoppt
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), false);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
  
  // 4. OPS wird alerted (Event)
  assert.strictEqual(events.length, 1);
  
  // 5. Investigation & Fix
  // (simuliert durch Health Mock)
  
  // 6. Reset versucht
  CircuitBreaker.attemptReset();
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN');
  
  // 7. Health checks OK
  const originalGetStatus = Health.getStatus;
  Health.getStatus = () => ({ isPaused: false, isMonitoring: true });
  
  // 8. Reset confirmed
  CircuitBreaker.confirmReset();
  Health.getStatus = originalGetStatus;
  
  // 9. Trading wieder erlaubt
  assert.strictEqual(CircuitBreaker.isTradingAllowed(), true);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED');
  
  // 10. Event chain complete
  assert.strictEqual(events.length, 3);
  assert.strictEqual(events[0].eventType, 'CIRCUIT_BREAKER_OPENED');
  assert.strictEqual(events[1].eventType, 'CIRCUIT_BREAKER_HALF_OPEN');
  assert.strictEqual(events[2].eventType, 'CIRCUIT_BREAKER_CLOSED');
});

// Final cleanup
test.after(async () => {
  if (CircuitBreaker) CircuitBreaker._reset();
});
