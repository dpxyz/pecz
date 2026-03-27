/**
 * Circuit Breaker Integration Tests
 * 
 * Coverage: Zustände, SAFETY vs OBSERVABILITY, Reset-Flow
 */

const test = require('node:test');
const assert = require('node:assert');

// Circuit Breaker vor jedem Test frisch laden
let CircuitBreaker;

function loadCB() {
  delete require.cache[require.resolve('../src/circuit_breaker.js')];
  CircuitBreaker = require('../src/circuit_breaker.js');
  CircuitBreaker._reset();
}

test.afterEach(async () => {
  if (CircuitBreaker) CircuitBreaker._reset();
});

// ============================================================================
// Tests
// ============================================================================

test('I1: Initial state is CLOSED', () => {
  loadCB();
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.state, 'CLOSED');
  assert.strictEqual(status.isTradingAllowed, true);
});

test('I2: SAFETY failure opens breaker', () => {
  loadCB();
  CircuitBreaker.recordSafetyFailure('event_store', { error: 'DB timeout' });
  
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.state, 'OPEN');
  assert.strictEqual(status.isTradingAllowed, false);
});

test('I3: OBSERVABILITY failure does NOT open breaker', () => {
  loadCB();
  // 10 OBSERVABILITY failures
  for (let i = 0; i < 10; i++) {
    CircuitBreaker.recordObservabilityFailure('discord_webhook');
  }
  
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.state, 'CLOSED');
  assert.strictEqual(status.isTradingAllowed, true);
  assert.strictEqual(status.failureCount, 0);
});

test('I4: attemptReset() moves OPEN → HALF_OPEN', () => {
  loadCB();
  CircuitBreaker.recordSafetyFailure('event_store');
  assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN');
  
  const result = CircuitBreaker.attemptReset();
  
  assert.strictEqual(result, true);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN');
});

test('I5: confirmReset() blocked when not in HALF_OPEN', () => {
  loadCB();
  // Von CLOSED aus
  const result = CircuitBreaker.confirmReset();
  assert.strictEqual(result, false);
  
  // Von OPEN aus
  CircuitBreaker.recordSafetyFailure('event_store');
  assert.strictEqual(result, false); // confirmReset() immer noch false
});

test('I6: attemptReset() ignored when not in OPEN', () => {
  loadCB();
  // Von CLOSED aus
  const result = CircuitBreaker.attemptReset();
  assert.strictEqual(result, false);
  assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED');
});

test('I7: Events captured via callback', () => {
  loadCB();
  const events = [];
  
  CircuitBreaker.configure({
    onStateChange: (eventType, data) => {
      events.push({ eventType, ...data });
    }
  });
  
  CircuitBreaker.recordSafetyFailure('event_store');
  
  assert.strictEqual(events.length, 1);
  assert.strictEqual(events[0].eventType, 'CIRCUIT_BREAKER_OPENED');
  assert.strictEqual(events[0].newState, 'OPEN');
});

test('I8: Exports API', () => {
  loadCB();
  assert.strictEqual(typeof CircuitBreaker.configure, 'function');
  assert.strictEqual(typeof CircuitBreaker.recordSafetyFailure, 'function');
  assert.strictEqual(typeof CircuitBreaker.recordObservabilityFailure, 'function');
  assert.strictEqual(typeof CircuitBreaker.attemptReset, 'function');
  assert.strictEqual(typeof CircuitBreaker.confirmReset, 'function');
  assert.strictEqual(typeof CircuitBreaker.isTradingAllowed, 'function');
  assert.strictEqual(typeof CircuitBreaker.getStatus, 'function');
  assert.strictEqual(typeof CircuitBreaker.States.CLOSED, 'string');
  assert.strictEqual(typeof CircuitBreaker.States.OPEN, 'string');
  assert.strictEqual(typeof CircuitBreaker.States.HALF_OPEN, 'string');
});

test('I9: Multiple SAFETY failures counted', () => {
  loadCB();
  CircuitBreaker.recordSafetyFailure('event_store');
  CircuitBreaker.recordSafetyFailure('watchdog_tick');
  
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.safetyFailureCount, 2);
});

test('I10: _reset() clears all state', () => {
  loadCB();
  CircuitBreaker.recordSafetyFailure('event_store');
  CircuitBreaker._reset();
  
  const status = CircuitBreaker.getStatus();
  assert.strictEqual(status.state, 'CLOSED');
  assert.strictEqual(status.failureCount, 0);
  assert.strictEqual(status.safetyFailureCount, 0);
});

// Cleanup
test.after(async () => {
  if (CircuitBreaker) CircuitBreaker._reset();
});
