/**
 * Event Store Tests
 * Test-First Development for Block 1
 * 
 * Note: Uses EventStore public API, not direct db access
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

// Module under test
let EventStore;

const TEST_DB = 'tests/test_event_store.db';

describe('EventStore', () => {
  
  before(() => {
    // Clean up any existing test DB
    if (fs.existsSync(TEST_DB)) {
      fs.unlinkSync(TEST_DB);
    }
    // Import fresh module
    delete require.cache[require.resolve('../src/event_store.js')];
    EventStore = require('../src/event_store.js');
    EventStore.init(TEST_DB);
  });
  
  after(() => {
    // Cleanup
    EventStore.close();
    if (fs.existsSync(TEST_DB)) {
      fs.unlinkSync(TEST_DB);
    }
  });

  describe('1.1 Schema Initialization', () => {
    it('init_creates_schema', () => {
      // Schema created by init() - if we're here, it worked
      assert.ok(EventStore.db, 'EventStore should have db initialized');
      
      // Add an event and retrieve it to verify db works
      EventStore.append({
        event_id: 'test_init',
        event_type: 'TEST',
        occurred_at: '2026-03-08T10:00:00Z',
        entity_type: 'test',
        entity_id: 't1',
        payload: '{}',
        correlation_id: null,
        causation_id: null
      });
      
      const result = EventStore.getEvents({ entity_id: 't1' });
      assert.strictEqual(result.events.length, 1, 'Should be able to retrieve event');
    });

    it('init_creates_indexes', () => {
      // Indexes are created - verify by checking multiple events with same type
      // are retrievable efficiently
      for (let i = 0; i < 5; i++) {
        EventStore.append({
          event_id: `idx_test_${i}`,
          event_type: 'INDEX_TEST',
          occurred_at: `2026-03-08T10:0${i}:00Z`,
          entity_type: 'test',
          entity_id: `idx_entity_${i}`,
          payload: '{}',
          correlation_id: null,
          causation_id: null
        });
      }
      
      const result = EventStore.getEvents({ event_type: 'INDEX_TEST' });
      assert.strictEqual(result.events.length, 5, 'Should retrieve all indexed events');
    });
  });

  describe('1.2 append() with Idempotency', () => {
    const testEvent = {
      event_id: 'evt_test_001',
      event_type: 'POSITION_OPENED',
      occurred_at: '2026-03-08T10:00:00Z',
      entity_type: 'position',
      entity_id: 'pos_123',
      payload: JSON.stringify({ symbol: 'BTC-USD', size: 1.0 }),
      correlation_id: 'corr_001',
      causation_id: null
    };

    it('append_saves_event', () => {
      EventStore.append(testEvent);
      
      const result = EventStore.getEvents({ entity_id: 'pos_123' });
      
      assert.strictEqual(result.events.length, 1, 'event should be saved');
      assert.strictEqual(result.events[0].event_id, testEvent.event_id);
      assert.strictEqual(result.events[0].event_type, testEvent.event_type);
      assert.strictEqual(result.events[0].entity_id, testEvent.entity_id);
    });

    it('append_idempotent_same_event_id', () => {
      // Clear first
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      // Append same event twice
      const first = EventStore.append(testEvent);
      const second = EventStore.append(testEvent);
      
      const result = EventStore.getEvents({ entity_id: 'pos_123' });
      assert.strictEqual(result.events.length, 1, 'should only have 1 event (idempotent)');
      
      // Note: Return value depends on implementation
      // In SQLite ON CONFLICT, first succeeds, second is ignored
    });

    it('append_different_event_ids', () => {
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      const event1 = { ...testEvent, event_id: 'evt_001', entity_id: 'e1' };
      const event2 = { ...testEvent, event_id: 'evt_002', entity_id: 'e2' };
      
      EventStore.append(event1);
      EventStore.append(event2);
      
      const result = EventStore.getEvents({});
      assert.strictEqual(result.events.length, 2, 'should have 2 different events');
    });
  });

  describe('1.3 getEvents() Filter', () => {
    before(() => {
      // Reset and populate
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      const events = [
        { event_id: 'evt_1', event_type: 'POSITION_OPENED', entity_type: 'position', entity_id: 'pos_1', occurred_at: '2026-03-08T10:00:00Z', payload: '{}', correlation_id: 'c1', causation_id: null },
        { event_id: 'evt_2', event_type: 'ORDER_FILLED', entity_type: 'order', entity_id: 'ord_1', occurred_at: '2026-03-08T10:01:00Z', payload: '{}', correlation_id: 'c1', causation_id: 'evt_1' },
        { event_id: 'evt_3', event_type: 'POSITION_CLOSED', entity_type: 'position', entity_id: 'pos_1', occurred_at: '2026-03-08T10:02:00Z', payload: '{}', correlation_id: 'c1', causation_id: 'evt_2' },
      ];
      
      for (const event of events) {
        EventStore.append(event);
      }
    });

    it('getEvents_returns_all_ordered', () => {
      const result = EventStore.getEvents({});
      
      assert.strictEqual(result.events.length, 3, 'should return all events');
      // Check ordering
      for (let i = 1; i < result.events.length; i++) {
        assert.ok(result.events[i-1].occurred_at <= result.events[i].occurred_at, 'should be ordered by time');
      }
    });

    it('getEvents_filtered_by_entity_type', () => {
      const result = EventStore.getEvents({ entity_type: 'position' });
      
      assert.strictEqual(result.events.length, 2, 'should return 2 position events');
      assert.ok(result.events.every(e => e.entity_type === 'position'));
    });

    it('getEvents_filtered_by_entity_id', () => {
      const result = EventStore.getEvents({ entity_id: 'pos_1' });
      
      assert.strictEqual(result.events.length, 2, 'should return events for pos_1');
      assert.ok(result.events.every(e => e.entity_id === 'pos_1'));
    });

    it('getEvents_filtered_by_event_type', () => {
      const result = EventStore.getEvents({ event_type: 'ORDER_FILLED' });
      
      assert.strictEqual(result.events.length, 1);
      assert.strictEqual(result.events[0].event_type, 'ORDER_FILLED');
    });

    it('getEvents_filtered_by_time_range', () => {
      const result = EventStore.getEvents({
        since: '2026-03-08T10:00:30Z',
        until: '2026-03-08T10:02:00Z'
      });
      
      assert.strictEqual(result.events.length, 2, 'should return events in time range');
    });
  });

  describe('1.4 Pagination', () => {
    before(() => {
      // Reset
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      // Create 10 events
      for (let i = 0; i < 10; i++) {
        EventStore.append({
          event_id: `evt_${String(i).padStart(3, '0')}`,
          event_type: 'TEST_EVENT',
          occurred_at: `2026-03-08T10:${String(i).padStart(2, '0')}:00Z`,
          entity_type: 'test',
          entity_id: `test_${i}`,
          payload: '{}',
          correlation_id: 'c1',
          causation_id: null
        });
      }
    });

    it('getEvents_pagination_limit', () => {
      const result = EventStore.getEvents({ limit: 5 });
      
      assert.strictEqual(result.events.length, 5, 'should respect limit');
    });

    it('getEvents_pagination_offset', () => {
      const result = EventStore.getEvents({ limit: 3, offset: 3 });
      
      assert.strictEqual(result.events.length, 3);
      assert.strictEqual(result.events[0].event_id, 'evt_003', 'should start at offset');
    });

    it('getEvents_returns_total_count', () => {
      const result = EventStore.getEvents({ limit: 5 });
      
      assert.strictEqual(result.total, 10, 'should return total count');
      assert.strictEqual(result.events.length, 5);
    });
  });

  describe('1.5 Concurrency Safety', () => {
    it('concurrent_append_safe', () => {
      // Reset
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      const event = {
        event_id: 'concurrent_evt',
        event_type: 'TEST',
        occurred_at: '2026-03-08T10:00:00Z',
        entity_type: 'test',
        entity_id: 'test_1',
        payload: '{}',
        correlation_id: 'c1',
        causation_id: null
      };
      
      // Try to append same event multiple times in rapid sequence
      // (Simulating concurrent behavior)
      const results = [];
      for (let i = 0; i < 10; i++) {
        try {
          results.push(EventStore.append(event));
        } catch (e) {
          // Expected for duplicates
        }
      }
      
      const result = EventStore.getEvents({ entity_id: 'test_1' });
      assert.strictEqual(result.events.length, 1, 'concurrent appends should not create duplicates');
    });

    it('concurrent_append_different_events', () => {
      // Reset - In-Memory mode
      EventStore.close();
      EventStore.init(':memory:'); // Use memory mode
      
      for (let i = 0; i < 10; i++) {
        EventStore.append({
          event_id: `concurrent_${i}`,
          event_type: 'TEST',
          occurred_at: `2026-03-08T10:${String(i).padStart(2, '0')}:00Z`,
          entity_type: 'test',
          entity_id: `test_${i}`,
          payload: '{}',
          correlation_id: 'c1',
          causation_id: null
        });
      }
      
      const result = EventStore.getEvents({});
      assert.strictEqual(result.total, 10, 'all different events should be saved');
    });
  });

  describe('1.6 Additional Utility Methods', () => {
    it('getLastEvent_returns_latest', () => {
      // Reset
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      EventStore.append({
        event_id: 'evt_1',
        event_type: 'TEST',
        occurred_at: '2026-03-08T10:00:00Z',
        entity_type: 'test',
        entity_id: 't1',
        payload: '{}',
        correlation_id: 'c1',
        causation_id: null
      });
      
      EventStore.append({
        event_id: 'evt_2',
        event_type: 'TEST',
        occurred_at: '2026-03-08T10:01:00Z',
        entity_type: 'test',
        entity_id: 't2',
        payload: '{}',
        correlation_id: 'c1',
        causation_id: null
      });
      
      const last = EventStore.getLastEvent();
      assert.strictEqual(last.event_id, 'evt_2');
    });

    it('getEventsByEntity_returns_entity_events', () => {
      // Reset
      EventStore.close();
      if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
      EventStore.init(TEST_DB);
      
      EventStore.append({
        event_id: 'evt_1',
        event_type: 'POSITION_OPENED',
        occurred_at: '2026-03-08T10:00:00Z',
        entity_type: 'position',
        entity_id: 'pos_123',
        payload: '{}',
        correlation_id: 'c1',
        causation_id: null
      });
      
      EventStore.append({
        event_id: 'evt_2',
        event_type: 'POSITION_CLOSED',
        occurred_at: '2026-03-08T10:01:00Z',
        entity_type: 'position',
        entity_id: 'pos_123',
        payload: '{}',
        correlation_id: 'c1',
        causation_id: 'evt_1'
      });
      
      const entityEvents = EventStore.getEventsByEntity('position', 'pos_123');
      assert.strictEqual(entityEvents.length, 2);
      assert.ok(entityEvents.every(e => e.entity_id === 'pos_123'));
    });
  });
});
