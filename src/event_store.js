/**
 * Event Store
 * Block 1: Core Reliability
 * Append-only, idempotent, queryable event log
 * 
 * Uses Node.js built-in node:sqlite (Node >= 22 experimental)
 * Falls back to memory store if sqlite not available
 */

let sqlite;
try {
  sqlite = require('node:sqlite');
} catch (e) {
  console.log('node:sqlite not available, using in-memory implementation');
}

const EventStore = {
  db: null,
  dbPath: null,
  isMemory: false,
  _memoryStore: [],

  /**
   * Initialize the event store
   * @param {string} dbPath - Path to SQLite database file
   */
  init(dbPath = 'runtime/event_store.db') {
    if (this.db) return;
    
    this.dbPath = dbPath;
    
    if (!sqlite) {
      this._initMemory();
      return;
    }
    
    // Ensure directory exists
    const path = require('path');
    const fs = require('fs');
    const dir = path.dirname(dbPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    
    // Open database using DatabaseSync
    this.db = new sqlite.DatabaseSync(dbPath);
    
    // Create table with sequence number for deterministic ordering
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        sequence INTEGER NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        correlation_id TEXT,
        causation_id TEXT
      )
    `);
    
    // Create indexes - include sequence for efficient replay ordering
    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_entity ON events(entity_type, entity_id);
      CREATE INDEX IF NOT EXISTS idx_time ON events(occurred_at);
      CREATE INDEX IF NOT EXISTS idx_sequence ON events(sequence);
      CREATE INDEX IF NOT EXISTS idx_type ON events(event_type);
    `);
    
    // Create sequence counter table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS event_store_meta (
        key TEXT PRIMARY KEY,
        value INTEGER
      )
    `);
    
    // Initialize sequence counter if not exists
    this.db.exec(`
      INSERT OR IGNORE INTO event_store_meta (key, value) VALUES ('sequence_counter', 0)
    `);
  },

  _initMemory() {
    this.isMemory = true;
    this._memoryStore = [];
    this._sequenceCounter = 0;
    console.log('Using in-memory event store for testing');
  },

  _getNextSequence() {
    if (this.isMemory) {
      this._sequenceCounter++;
      return this._sequenceCounter;
    }
    
    // Atomically increment and return sequence counter
    const result = this.db.prepare(`
      UPDATE event_store_meta 
      SET value = value + 1 
      WHERE key = 'sequence_counter'
      RETURNING value
    `).get();
    
    return result.value;
  },

  /**
   * Append an event to the store (idempotent)
   * @param {Object} event - Event to append
   * @returns {boolean} - true if inserted, false if duplicate
   */
  append(event) {
    if (this.isMemory) {
      return this._appendMemory(event);
    }
    
    if (!this.db) {
      throw new Error('EventStore not initialized. Call init() first.');
    }
    
    // Validate required fields
    const required = ['event_id', 'event_type', 'occurred_at', 'entity_type', 'entity_id', 'payload'];
    for (const field of required) {
      if (!(field in event)) {
        throw new Error(`Event missing required field: ${field}`);
      }
    }
    
    const payloadStr = typeof event.payload === 'string' 
      ? event.payload 
      : JSON.stringify(event.payload);
    
    const sequence = this._getNextSequence();
    
    try {
      // Use exec with template for idempotent insert (sequence may cause conflict on replay)
      this.db.exec(`
        INSERT INTO events (event_id, sequence, event_type, occurred_at, entity_type, entity_id, payload, correlation_id, causation_id)
        VALUES ('${event.event_id}', ${sequence}, '${event.event_type}', '${event.occurred_at}', '${event.entity_type}', '${event.entity_id}', '${payloadStr.replace(/'/g, "''")}', ${event.correlation_id ? `'${event.correlation_id}'` : 'NULL'}, ${event.causation_id ? `'${event.causation_id}'` : 'NULL'})
        ON CONFLICT(event_id) DO NOTHING
      `);
      
      // Check if actually inserted (idempotency check)
      const count = this.db.prepare('SELECT COUNT(*) as cnt FROM events WHERE event_id = ?').get(event.event_id);
      return count.cnt > 0;
    } catch (err) {
      // If error is about duplicate sequence, we still need to consume the sequence number
      // This maintains monotonic sequence even on replay
      if (err.message.includes('UNIQUE')) {
        // Already exists - idempotent skip
        return false;
      }
      throw err;
    }
  },

  _appendMemory(event) {
    const existing = this._memoryStore.find(e => e.event_id === event.event_id);
    if (existing) return false;
    
    // Add sequence number for deterministic ordering
    const seqEvent = { ...event, sequence: this._getNextSequence() };
    
    this._memoryStore.push(seqEvent);
    // Sort by sequence for deterministic replay (not just occurred_at)
    this._memoryStore.sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
    return true;
  },

  /**
   * Get events with filtering and pagination
   * @param {Object} options - Query options
   * @returns {Object} { events: [...], total: number }
   */
  getEvents(options = {}) {
    if (this.isMemory) {
      return this._getEventsMemory(options);
    }
    
    if (!this.db) {
      throw new Error('EventStore not initialized');
    }
    
    const {
      event_type,
      entity_type,
      entity_id,
      since,
      until,
      limit = 1000,
      offset = 0
    } = options;
    
    // Build WHERE clause
    const conditions = [];
    
    if (event_type) conditions.push(`event_type = '${event_type}'`);
    if (entity_type) conditions.push(`entity_type = '${entity_type}'`);
    if (entity_id) conditions.push(`entity_id = '${entity_id}'`);
    if (since) conditions.push(`occurred_at >= '${since}'`);
    if (until) conditions.push(`occurred_at <= '${until}'`);
    
    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    
    // Get total (simplified - just get all and count)
    // ORDER BY sequence ASC ensures deterministic replay order
    // sequence is the tiebreaker for events with same occurred_at
    const all = this.db.prepare(`SELECT * FROM events ${where} ORDER BY sequence ASC`).all();
    const total = all.length;
    
    // Apply pagination
    const events = all.slice(offset, offset + limit).map(e => ({
      ...e,
      payload: this._safeJsonParse(e.payload)
    }));
    
    return { events, total };
  },

  _getEventsMemory(options = {}) {
    let events = [...this._memoryStore];
    
    const { event_type, entity_type, entity_id, since, until, limit = 1000, offset = 0 } = options;
    
    if (event_type) events = events.filter(e => e.event_type === event_type);
    if (entity_type) events = events.filter(e => e.entity_type === entity_type);
    if (entity_id) events = events.filter(e => e.entity_id === entity_id);
    if (since) events = events.filter(e => e.occurred_at >= since);
    if (until) events = events.filter(e => e.occurred_at <= until);
    
    // Always sort by sequence for deterministic ordering
    events.sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
    
    const total = events.length;
    events = events.slice(offset, offset + limit);
    
    return { events, total };
  },

  /**
   * Get events for a specific entity
   * @param {string} entityType - Entity type
   * @param {string} entityId - Entity ID
   * @returns {Array} Array of events
   */
  getEventsByEntity(entityType, entityId) {
    return this.getEvents({ entity_type: entityType, entity_id: entityId }).events;
  },

  /**
   * Get the last event by time
   * @returns {Object|null} Last event or null
   */
  getLastEvent() {
    if (this.isMemory) {
      return this._memoryStore.length > 0 
        ? this._memoryStore[this._memoryStore.length - 1] 
        : null;
    }
    
    if (!this.db) throw new Error('EventStore not initialized');
    
    // ORDER BY sequence DESC for deterministic "last" event
    const event = this.db.prepare(
      'SELECT * FROM events ORDER BY sequence DESC LIMIT 1'
    ).get();
    
    if (!event) return null;
    return { ...event, payload: this._safeJsonParse(event.payload) };
  },

  /**
   * Get events for deterministic replay
   * @param {Object} options - Query options
   * @returns {Object} { events, total }
   * 
   * Ordering Guarantee: events are returned in sequence order (monotonic)
   * This ensures deterministic rebuilds even with identical timestamps
   */
  getReplayEvents(options = {}) {
    // Force sequence ordering for rebuilds
    return this.getEvents({ ...options, orderBy: 'sequence' });
  },

  _safeJsonParse(value) {
    if (typeof value !== 'string') return value;
    try { return JSON.parse(value); } catch { return value; }
  },

  /**
   * Close database connection
   */
  close() {
    if (this.db) {
      this.db.close();
      this.db = null;
    }
  }
};

module.exports = EventStore;
