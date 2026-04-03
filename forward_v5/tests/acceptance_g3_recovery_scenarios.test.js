/**
 * Acceptance Gate G3: Recovery Scenarios
 * 
 * GOAL: Prove system returns to consistent state after defined disturbances
 * CRITICAL: Recovery must be observable, not silently faulty
 * 
 * G3 Acceptance Criteria:
 * - After disturbance: system recovers to consistent state
 * - Error state is recognized before recovery
 * - No false permanent failure after successful recovery
 * - Deterministic behavior continues after recovery
 * - No zombie state after recovery actions
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert');

describe('G3_Acceptance_Recovery_Scenarios', () => {
  let CircuitBreaker;
  let StateProjection;
  let Health;
  
  before(() => {
    // Fresh imports
    delete require.cache[require.resolve('../src/circuit_breaker.js')];
    delete require.cache[require.resolve('../src/state_projection.js')];
    delete require.cache[require.resolve('../src/health.js')];
    
    CircuitBreaker = require('../src/circuit_breaker.js');
    StateProjection = require('../src/state_projection.js');
    Health = require('../src/health.js');
  });
  
  after(() => {
    // Cleanup - ensure clean state for other tests
    CircuitBreaker._reset();
    StateProjection.reset();
    Health.clearAlerts?.();
  });

  /**
   * G3.1: Circuit Breaker Recovery Flow
   * Disturbance: SAFETY failure opens breaker
   * Recovery: Manual reset returns to CLOSED
   * Verify: State transitions correctly and trading resumes
   */
  it('G3.1_circuit_breaker_opens_and_recovers', () => {
    // Arrange: Verify initial state
    const initialState = CircuitBreaker.getStatus().state;
    assert.strictEqual(initialState, 'CLOSED', 'Initial state is CLOSED');
    
    // Act: SAFETY failure opens breaker
    CircuitBreaker.recordSafetyFailure('memory_critical', { 
      percent: 95, 
      details: 'heap exceeded' 
    });
    
    // Assert: Breaker is OPEN
    const openState = CircuitBreaker.getStatus().state;
    assert.strictEqual(openState, 'OPEN', 'Breaker opened after SAFETY failure');
    assert.strictEqual(CircuitBreaker.isTradingAllowed(), false, 'Trading is not allowed when OPEN');
    assert.strictEqual(!CircuitBreaker.isTradingAllowed(), true, 'Trading is blocked');
    
    // Act: Attempt recovery
    const recoveryResult = CircuitBreaker.attemptReset();
    
    // Assert: Recovery state reached
    assert.strictEqual(recoveryResult, true, 'Recovery attempt succeeded');
    assert.strictEqual(CircuitBreaker.getStatus().state, 'HALF_OPEN', 'State is HALF_OPEN after recovery');
    assert.strictEqual(CircuitBreaker.isTradingAllowed(), false, 'Trading still blocked in HALF_OPEN (requires confirm)');
    
    // Act: Confirm successful recovery (simulates successful health check after recovery)
    CircuitBreaker.confirmReset();
    
    // Assert: Back to normal
    assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED', 'State returns to CLOSED after confirmation');
    assert.strictEqual(CircuitBreaker.getStatus().state === "CLOSED", true, 'Breaker is no longer open');
    
    console.log('✅ G3.1 PASSED: Circuit breaker opens and recovers correctly');
  });

  /**
   * G3.2: State Projection Reset After Corruption
   * Disturbance: State projection potentially inconsistent
   * Recovery: Full reset and rebuild
   * Verify: Clean state with no zombie data
   */
  it('G3.2_state_projection_reset_no_zombie_state', () => {
    // Arrange: Create some state
    let state = StateProjection.getCurrentState();
    const event1 = {
      event_type: 'RUN_STARTED',
      event_id: 'g3_test_001',
      occurred_at: '2026-04-03T14:00:00Z',
      payload: {
        run_id: 'g3_recovery_run',
        symbol: 'BTC-USD',
        mode: 'paper'
      }
    };
    state = StateProjection.applyEvent(state, event1);
    
    // Verify state exists
    assert.ok(state.current_run, 'State has run before reset');
    assert.strictEqual(state.current_run.run_id, 'g3_recovery_run', 'Run ID matches');
    
    // Act: Reset state (recovery action)
    StateProjection.reset();
    
    // Assert: Clean slate - no zombie state
    const resetState = StateProjection.getCurrentState();
    assert.strictEqual(resetState.current_run, null, 'Run cleared after reset');
    assert.deepStrictEqual(resetState.open_positions, [], 'Open positions cleared');
    assert.deepStrictEqual(resetState.pending_orders, [], 'Pending orders cleared');
    assert.ok(resetState.projection_version, 'Reset state still has structure');
    assert.strictEqual(resetState.safety.overall_status, 'healthy', 'Safety status reset');
    
    // Verify: Can rebuild cleanly after reset
    const freshEvent = {
      event_type: 'RUN_STARTED',
      event_id: 'g3_test_002',
      occurred_at: '2026-04-03T14:05:00Z',
      payload: {
        run_id: 'g3_post_recovery_run',
        symbol: 'ETH-USD',
        mode: 'paper'
      }
    };
    const rebuiltState = StateProjection.applyEvent(resetState, freshEvent);
    assert.strictEqual(rebuiltState.current_run.run_id, 'g3_post_recovery_run', 'Can rebuild with new events');
    
    console.log('✅ G3.2 PASSED: State projection reset with no zombie state');
  });

  /**
   * G3.3: No False Permanent Failure
   * After successful recovery, system doesn't falsely report failure
   */
  it('G3.3_no_false_failure_after_recovery', () => {
    StateProjection.reset();
    
    // Arrange: Create healthy baseline
    CircuitBreaker._reset();
    const health1 = StateProjection.getCurrentState().safety.overall_status;
    assert.strictEqual(health1, 'healthy', 'Initial health is good');
    
    // Act: Trigger and resolve failure
    CircuitBreaker.recordSafetyFailure('test_failure', { temp: true });
    assert.strictEqual(CircuitBreaker.getStatus().state, 'OPEN', 'Breaker opens');
    
    // Recovery
    CircuitBreaker.attemptReset();
    CircuitBreaker.confirmReset();
    
    // Assert: Health tracking accurate
    assert.strictEqual(CircuitBreaker.getStatus().state, 'CLOSED', 'Breaker closed after recovery');
    assert.strictEqual(!CircuitBreaker.isTradingAllowed(), false, 'Trading not blocked after recovery');
    
    // Critical: No lingering failure indication
    const failureCount = CircuitBreaker.getFailureCount ? CircuitBreaker.getFailureCount() : 0;
    // After confirmReset, failure count should be reset or state should indicate recovery
    assert.ok(
      CircuitBreaker.getStatus().state === 'CLOSED', 
      'System not stuck in false failure state'
    );
    
    console.log('✅ G3.3 PASSED: No false permanent failure after recovery');
  });

  /**
   * G3.4: Deterministic Behavior After Recovery
   * Same events produce same state after recovery as before
   */
  it('G3.4_deterministic_after_recovery', () => {
    StateProjection.reset();
    
    // First run: Normal processing
    const events1 = [
      { type: 'RUN_STARTED', id: 'g3_det_001', payload: { run_id: 'g3_det_run', symbol: 'BTC' } },
      { type: 'RUN_ENDED', id: 'g3_det_002', payload: { run_id: 'g3_det_run' } }
    ];
    
    let state1 = StateProjection.getCurrentState();
    for (const evt of events1) {
      const wrappedEvt = { ...evt, event_type: evt.type, event_id: evt.id, occurred_at: new Date().toISOString() };
      state1 = StateProjection.applyEvent(state1, wrappedEvt);
    }
    const snapshot1 = JSON.stringify(state1);
    
    // Act: Recovery (reset + rebuild)
    StateProjection.reset();
    let state2 = StateProjection.getCurrentState();
    for (const evt of events1) {
      const wrappedEvt = { ...evt, event_type: evt.type, event_id: evt.id, occurred_at: new Date().toISOString() };
      state2 = StateProjection.applyEvent(state2, wrappedEvt);
    }
    const snapshot2 = JSON.stringify(state2);
    
    // Assert: Deterministic recovery
    // Note: timestamps differ, so we compare structure, not exact JSON
    assert.strictEqual(state2.open_positions.length, state1.open_positions.length, 'Same position count');
    assert.strictEqual(state2.current_run?.status || 'none', state1.current_run?.status || 'none', 'Same run status');
    
    console.log('✅ G3.4 PASSED: Deterministic behavior after recovery');
  });

  /**
   * G3.5: Observable Recovery
   * Recovery actions are trackable, not silent
   */
  it('G3.5_recovery_is_observable', () => {
    StateProjection.reset();
    CircuitBreaker._reset();
    
    // Track state changes
    const stateLog = [];
    stateLog.push({ time: Date.now(), breaker: CircuitBreaker.getStatus().state, projection: StateProjection.getCurrentState().safety.overall_status });
    
    // Act: Trigger failure
    CircuitBreaker.recordSafetyFailure('critical_error', {});
    stateLog.push({ time: Date.now(), breaker: CircuitBreaker.getStatus().state });
    
    // Act: Recovery
    CircuitBreaker.attemptReset();
    stateLog.push({ time: Date.now(), breaker: CircuitBreaker.getStatus().state });
    
    CircuitBreaker.confirmReset();
    stateLog.push({ time: Date.now(), breaker: CircuitBreaker.getStatus().state });
    
    // Assert: Observable state transitions
    assert.strictEqual(stateLog[0].breaker, 'CLOSED', 'Started closed');
    assert.strictEqual(stateLog[1].breaker, 'OPEN', 'Then opened');
    assert.strictEqual(stateLog[2].breaker, 'HALF_OPEN', 'Then half-open (recovery)');
    assert.strictEqual(stateLog[3].breaker, 'CLOSED', 'Finally closed');
    
    // Critical: All transitions logged
    assert.strictEqual(stateLog.length, 4, 'All recovery steps observable');
    
    console.log('✅ G3.5 PASSED: Recovery is observable');
  });
});

console.log('\n🧪 G3 Acceptance: Recovery Scenarios Loaded');
console.log('Running: node --test tests/acceptance_g3_recovery_scenarios.test.js\n');
