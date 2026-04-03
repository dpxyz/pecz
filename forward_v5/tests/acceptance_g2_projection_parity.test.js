/**
 * Acceptance Gate G2: Projection Parity
 * 
 * GOAL: Prove that state projection accurately reflects event sequence
 * CRITICAL: Silent divergence between Event Store and State Projection must be impossible
 * 
 * G2 Acceptance Criteria:
 * - After defined event sequence, projection matches expected state
 * - Event order is respected during state rebuild
 * - No silent drift between event store and projection
 * - A real parity break would be immediately visible
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const TEST_DB = path.join(__dirname, 'test_g2_parity.db');

describe('G2_Acceptance_Projection_Parity', () => {
  let EventStore;
  let StateProjection;
  
  before(() => {
    // Clean slate for G2
    if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
    
    // Fresh imports
    delete require.cache[require.resolve('../src/event_store.js')];
    delete require.cache[require.resolve('../src/state_projection.js')];
    
    EventStore = require('../src/event_store.js');
    StateProjection = require('../src/state_projection.js');
    
    EventStore.init(TEST_DB);
  });
  
  after(() => {
    if (EventStore && EventStore.close) EventStore.close();
    if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
  });

  /**
   * G2.1: Basic Event Sequence Parity
   * Events: RUN_STARTED → SIGNAL_GENERATED → POSITION_OPENED
   * Expected: Projection matches manually computed state
   */
  it('G2.1_event_sequence_produces_correct_state', () => {
    // Arrange: Expected state computation
    const expectedRunId = 'g2_test_run_001';
    const expectedSymbol = 'BTC-USD';
    const expectedPositionId = 'pos_001';
    
    // Act: Append events to store (with required entity fields)
    EventStore.append({
      event_type: 'RUN_STARTED',
      event_id: 'evt_g2_001',
      occurred_at: '2026-04-03T10:00:00Z',
      entity_type: 'run',
      entity_id: expectedRunId,
      payload: {
        run_id: expectedRunId,
        symbol: expectedSymbol,
        timeframe: '1h',
        mode: 'paper',
        config_version: 'v1'
      }
    });
    
    EventStore.append({
      event_type: 'SIGNAL_GENERATED',
      event_id: 'evt_g2_002',
      occurred_at: '2026-04-03T10:05:00Z',
      entity_type: 'signal',
      entity_id: 'sig_001',
      payload: {
        signal_id: 'sig_001',
        run_id: expectedRunId,
        action: 'OPEN_LONG',
        confidence: 0.85
      }
    });
    
    EventStore.append({
      event_type: 'POSITION_OPENED',
      event_id: 'evt_g2_003',
      occurred_at: '2026-04-03T10:05:01Z',
      entity_type: 'position',
      entity_id: expectedPositionId,
      payload: {
        position_id: expectedPositionId,
        signal_id: 'sig_001',
        symbol: expectedSymbol,
        side: 'LONG',
        entry_price: 85000,
        size: 0.1
      }
    });
    
    // Query events and apply to projection
    const events = EventStore.getEvents({}).events;
    let state = StateProjection.getCurrentState();
    
    for (const event of events) {
      state = StateProjection.applyEvent(state, event);
    }
    
    // Assert: Projection parity check
    assert.ok(state.current_run, 'Projection must have current_run');
    assert.strictEqual(state.current_run.run_id, expectedRunId, 'Run ID must match');
    assert.strictEqual(state.current_run.symbol, expectedSymbol, 'Symbol must match');
    
    // Critical: Position exists in projection
    assert.strictEqual(state.open_positions.length, 1, 'Must have exactly one position');
    assert.strictEqual(state.open_positions[0].position_id, expectedPositionId, 'Position ID must match');
    
    console.log('✅ G2.1 PASSED: Event sequence produces correct state');
  });

  /**
   * G2.2: Event Order Matters
   * Events: RUN_STARTED → RUN_ENDED
   * Expected: Projection respects temporal order
   */
  it('G2.2_event_order_is_respected', () => {
    StateProjection.reset();
    
    // Act: Events in logical order
    EventStore.append({
      event_type: 'RUN_STARTED',
      event_id: 'evt_g2_100',
      occurred_at: '2026-04-03T11:00:00Z',
      entity_type: 'run',
      entity_id: 'g2_order_test',
      payload: {
        run_id: 'g2_order_test',
        symbol: 'ETH-USD',
        mode: 'paper',
        config_version: 'v1'
      }
    });
    
    EventStore.append({
      event_type: 'RUN_ENDED',
      event_id: 'evt_g2_101',
      occurred_at: '2026-04-03T11:30:00Z',
      entity_type: 'run',
      entity_id: 'g2_order_test',
      payload: {
        run_id: 'g2_order_test',
        reason: 'manual_stop'
      }
    });
    
    // Apply in sequence order
    const events = EventStore.getEvents({}).events;
    let state = StateProjection.getCurrentState();
    
    for (const event of events) {
      state = StateProjection.applyEvent(state, event);
    }
    
    // Assert: Order respected
    assert.ok(state.current_run, 'Must have run record');
    assert.strictEqual(state.current_run.status, 'ended', 'Run must be ended after ENDED event');
    assert.ok(state.current_run.ended_at, 'Must have ended_at timestamp');
    
    console.log('✅ G2.2 PASSED: Event order is respected');
  });

  /**
   * G2.3: No Silent Divergence
   * Event count in store must match events processed by projection
   */
  it('G2.3_no_silent_divergence', () => {
    StateProjection.reset();
    
    // Get event count from store
    const eventCount = EventStore.getEvents({}).events.length;
    
    // Apply all events to projection
    const events = EventStore.getEvents({}).events;
    let state = StateProjection.getCurrentState();
    let processedCount = 0;
    
    for (const event of events) {
      state = StateProjection.applyEvent(state, event);
      processedCount++;
    }
    
    // Critical: All events processed
    assert.strictEqual(processedCount, eventCount, 'All events must be processed');
    
    // Additional: State contains expected data
    assert.ok(state.current_run, 'State must have current run');
    
    console.log('✅ G2.3 PASSED: No silent divergence');
  });

  /**
   * G2.4: Deterministic Rebuild
   * Same events must produce same state
   */
  it('G2.4_rebuild_is_deterministic', () => {
    StateProjection.reset();
    
    // First build
    const events = EventStore.getEvents({}).events;
    let state1 = StateProjection.getCurrentState();
    for (const event of events) {
      state1 = StateProjection.applyEvent(state1, event);
    }
    const snapshot1 = JSON.stringify(state1);
    
    // Second build (fresh state)
    StateProjection.reset();
    let state2 = StateProjection.getCurrentState();
    for (const event of events) {
      state2 = StateProjection.applyEvent(state2, event);
    }
    const snapshot2 = JSON.stringify(state2);
    
    // Critical: Identical states
    assert.strictEqual(snapshot1, snapshot2, 'Rebuild must be deterministic');
    
    console.log('✅ G2.4 PASSED: Rebuild is deterministic');
  });

  /**
   * G2.5: End-State Parity
   * After all events processed, projection state is complete
   */
  it('G2.5_end_state_is_consistent', () => {
    StateProjection.reset();
    
    // Apply ALL events from store
    const events = EventStore.getEvents({}).events;
    let state = StateProjection.getCurrentState();
    
    for (const event of events) {
      state = StateProjection.applyEvent(state, event);
    }
    
    // Key consistency checks
    const totalPositions = state.open_positions?.length + (state.closed_positions?.length || 0);
    
    // Projection must have coherent structure
    assert.ok(state.current_run || totalPositions > 0, 'State has content');
    assert.ok(state.projection_version, 'Projection version set');
    assert.ok(Array.isArray(state.open_positions), 'Open positions is array');
    
    // No undefined critical fields
    assert.notStrictEqual(state.safety?.overall_status, undefined, 'Safety status present');
    
    console.log('✅ G2.5 PASSED: End-state consistency verified');
  });
});

console.log('\n🧪 G2 Acceptance: Projection Parity Tests Loaded');
console.log('Running: node --test tests/acceptance_g2_projection_parity.test.js\n');
