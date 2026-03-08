/**
 * State Projection
 * Block 2: Core Reliability
 * 
 * Deterministic Event → State Reducer
 * Single source of truth: Event Store
 * Side-effect-free, pure functions only
 */

const EventStore = require('./event_store.js');

const StateProjection = {
  // Current projected state (in-memory cache)
  _state: null,
  _lastEventId: null,
  _lastSequence: null,
  
  /**
   * Event Reducers
   * Pure functions: (state, event) => newState
   * No side effects, no mutations of input state
   */
  reducers: {
    // Run Lifecycle
    RUN_STARTED: (state, event) => {
      const newState = deepClone(state);
      newState.current_run = {
        run_id: event.payload.run_id,
        started_at: event.payload.started_at,
        ended_at: null,
        symbol: event.payload.symbol,
        timeframe: event.payload.timeframe,
        mode: event.payload.mode,
        config_version: event.payload.config_version
      };
      return newState;
    },

    RUN_PAUSED: (state, event) => {
      const newState = deepClone(state);
      if (newState.current_run) {
        newState.current_run.status = 'paused';
      }
      return newState;
    },

    RUN_RESUMED: (state, event) => {
      const newState = deepClone(state);
      if (newState.current_run) {
        newState.current_run.status = 'active';
      }
      return newState;
    },

    RUN_ENDED: (state, event) => {
      const newState = deepClone(state);
      if (newState.current_run) {
        newState.current_run.ended_at = event.occurred_at;
        newState.current_run.status = 'ended';
      }
      return newState;
    },

    // Signals
    SIGNAL_GENERATED: (state, event) => {
      const newState = deepClone(state);
      newState.recent_signals.unshift({
        signal_id: event.payload.signal_id,
        run_id: event.payload.run_id,
        timestamp: event.payload.timestamp,
        action: event.payload.action,
        confidence: event.payload.confidence,
        metadata: event.payload.metadata
      });
      // Keep only last N signals
      if (newState.recent_signals.length > 100) {
        newState.recent_signals = newState.recent_signals.slice(0, 100);
      }
      return newState;
    },

    SIGNAL_REJECTED: (state, event) => {
      // Signal rejected - just log, no state change
      return deepClone(state);
    },

    // Intents
    INTENT_CREATED: (state, event) => {
      const newState = deepClone(state);
      newState.recent_intents.unshift({
        intent_id: event.payload.intent_id,
        signal_id: event.payload.signal_id,
        run_id: event.payload.run_id,
        action: event.payload.action,
        target_size: event.payload.target_size,
        reason: event.payload.reason,
        risk_check_passed: event.payload.risk_check_passed
      });
      if (newState.recent_intents.length > 100) {
        newState.recent_intents = newState.recent_intents.slice(0, 100);
      }
      return newState;
    },

    INTENT_REJECTED: (state, event) => {
      // Intent rejected - log only
      return deepClone(state);
    },

    // Orders
    ORDER_CREATED: (state, event) => {
      const newState = deepClone(state);
      newState.pending_orders.push({
        order_id: event.payload.order_id,
        position_id: event.payload.position_id,
        symbol: event.payload.symbol,
        side: event.payload.side,
        type: event.payload.type,
        size: event.payload.size,
        price: event.payload.price,
        status: 'created',
        created_at: event.occurred_at
      });
      return newState;
    },

    ORDER_SENT: (state, event) => {
      const newState = deepClone(state);
      const order = newState.pending_orders.find(o => o.order_id === event.payload.order_id);
      if (order) {
        order.status = 'sent';
        order.sent_at = event.occurred_at;
      }
      return newState;
    },

    ORDER_ACK: (state, event) => {
      const newState = deepClone(state);
      const order = newState.pending_orders.find(o => o.order_id === event.payload.order_id);
      if (order) {
        order.status = 'pending';
        order.ack_at = event.occurred_at;
      }
      return newState;
    },

    ORDER_FILLED: (state, event) => {
      const newState = deepClone(state);
      const orderIndex = newState.pending_orders.findIndex(o => o.order_id === event.payload.order_id);
      
      if (orderIndex >= 0) {
        const order = newState.pending_orders[orderIndex];
        order.status = 'filled';
        order.filled_size = event.payload.filled_size;
        order.avg_fill_price = event.payload.avg_fill_price;
        order.updated_at = event.occurred_at;
        
        // Remove from pending once filled
        newState.pending_orders.splice(orderIndex, 1);
      }
      
      return newState;
    },

    ORDER_PARTIAL_FILL: (state, event) => {
      const newState = deepClone(state);
      const order = newState.pending_orders.find(o => o.order_id === event.payload.order_id);
      
      if (order) {
        order.status = 'partial';
        order.filled_size = event.payload.filled_size;
        order.avg_fill_price = event.payload.avg_fill_price;
        order.updated_at = event.occurred_at;
      }
      
      return newState;
    },

    ORDER_CANCELED: (state, event) => {
      const newState = deepClone(state);
      const index = newState.pending_orders.findIndex(o => o.order_id === event.payload.order_id);
      
      if (index >= 0) {
        newState.pending_orders.splice(index, 1);
      }
      
      return newState;
    },

    ORDER_REJECTED: (state, event) => {
      const newState = deepClone(state);
      const index = newState.pending_orders.findIndex(o => o.order_id === event.payload.order_id);
      
      if (index >= 0) {
        newState.pending_orders.splice(index, 1);
      }
      
      return newState;
    },

    // Positions
    POSITION_OPENED: (state, event) => {
      const newState = deepClone(state);
      
      newState.open_positions.push({
        position_id: event.payload.position_id,
        run_id: event.payload.run_id,
        symbol: event.payload.symbol,
        side: event.payload.side,
        entry_price: event.payload.entry_price,
        size: event.payload.size,
        realized_pnl: 0,
        unrealized_pnl: 0,
        opened_at: event.occurred_at,
        closed_at: null,
        status: 'open',
        orders: event.payload.orders || []
      });
      
      return newState;
    },

    POSITION_SIZE_CHANGED: (state, event) => {
      const newState = deepClone(state);
      const position = newState.open_positions.find(p => p.position_id === event.payload.position_id);
      
      if (position) {
        position.size = event.payload.new_size;
        position.realized_pnl = event.payload.realized_pnl || position.realized_pnl;
      }
      
      return newState;
    },

    POSITION_CLOSED: (state, event) => {
      const newState = deepClone(state);
      const positionIndex = newState.open_positions.findIndex(
        p => p.position_id === event.payload.position_id
      );
      
      if (positionIndex >= 0) {
        const position = newState.open_positions[positionIndex];
        position.status = 'closed';
        position.closed_at = event.occurred_at;
        position.realized_pnl = event.payload.realized_pnl;
        
        // Move to closed positions history (optional)
        // For now keep in place for simplicity
      }
      
      return newState;
    },

    POSITION_LIQUIDATED: (state, event) => {
      const newState = deepClone(state);
      const position = newState.open_positions.find(
        p => p.position_id === event.payload.position_id
      );
      
      if (position) {
        position.status = 'liquidated';
        position.closed_at = event.occurred_at;
        position.realized_pnl = event.payload.realized_pnl;
      }
      
      return newState;
    },

    // Health
    HEALTH_CHECK_PASSED: (state, event) => {
      const newState = deepClone(state);
      newState.current_health = {
        health_id: event.payload.health_id,
        run_id: event.payload.run_id,
        timestamp: event.occurred_at,
        safety_status: event.payload.safety_status,
        observability_status: event.payload.observability_status,
        last_tick_at: event.payload.last_tick_at,
        last_report_at: event.payload.last_report_at
      };
      return newState;
    },

    HEALTH_CHECK_FAILED: (state, event) => {
      const newState = deepClone(state);
      if (newState.current_health) {
        newState.current_health.status = 'failed';
        newState.current_health.failure_reason = event.payload.reason;
      }
      return newState;
    },

    // Config
    CONFIG_LOADED: (state, event) => {
      const newState = deepClone(state);
      newState.active_config = {
        config_id: event.payload.config_id,
        loaded_at: event.payload.loaded_at,
        active: true,
        ...event.payload.config
      };
      return newState;
    },

    CONFIG_CHANGED: (state, event) => {
      const newState = deepClone(state);
      if (newState.active_config) {
        newState.active_config.active = false;
      }
      newState.active_config = {
        config_id: event.payload.config_id,
        loaded_at: event.occurred_at,
        active: true,
        ...event.payload.config
      };
      return newState;
    },

    // Safety
    SAFETY_VIOLATED: (state, event) => {
      const newState = deepClone(state);
      
      newState.safety.active_violations.push({
        type: event.payload.gate,
        severity: event.payload.severity, // 'block' or 'warn'
        detected_at: event.occurred_at,
        message: event.payload.message
      });
      
      // Update overall status
      if (event.payload.severity === 'block') {
        newState.safety.overall_status = 'critical';
        newState.safety.block_trading = true;
      } else if (newState.safety.overall_status === 'healthy') {
        newState.safety.overall_status = 'degraded';
      }
      
      return newState;
    },

    SAFETY_RESOLVED: (state, event) => {
      const newState = deepClone(state);
      
      // Remove the resolved violation
      newState.safety.active_violations = newState.safety.active_violations.filter(
        v => v.type !== event.payload.gate
      );
      
      // Recalculate status
      const hasBlock = newState.safety.active_violations.some(v => v.severity === 'block');
      const hasWarn = newState.safety.active_violations.some(v => v.severity === 'warn');
      
      if (hasBlock) {
        newState.safety.overall_status = 'critical';
        newState.safety.block_trading = true;
      } else if (hasWarn) {
        newState.safety.overall_status = 'degraded';
        newState.safety.block_trading = false;
      } else {
        newState.safety.overall_status = 'healthy';
        newState.safety.block_trading = false;
      }
      
      return newState;
    },

    // Observability
    OBSERVABILITY_WARN: (state, event) => {
      const newState = deepClone(state);
      
      newState.observability.active_warnings.push({
        type: event.payload.gate,
        severity: 'warn',
        detected_at: event.occurred_at,
        message: event.payload.message
      });
      
      if (newState.observability.overall_status === 'healthy') {
        newState.observability.overall_status = 'degraded';
      }
      
      return newState;
    },

    OBSERVABILITY_RESOLVED: (state, event) => {
      const newState = deepClone(state);
      
      newState.observability.active_warnings = newState.observability.active_warnings.filter(
        w => w.type !== event.payload.gate
      );
      
      if (newState.observability.active_warnings.length === 0) {
        newState.observability.overall_status = 'healthy';
      }
      
      return newState;
    }
  },

  /**
   * Apply single event to state using appropriate reducer
   * @param {Object} state - Current state
   * @param {Object} event - Event to apply
   * @returns {Object} New state (immutable)
   */
  applyEvent(state, event) {
    const reducer = this.reducers[event.event_type];
    
    if (!reducer) {
      // Unknown event type - return unchanged state (forward compatibility)
      console.warn(`No reducer for event type: ${event.event_type}`);
      return deepClone(state);
    }
    
    return reducer(state, event);
  },

  /**
   * Project multiple events onto initial state
   * Deterministic: same events + same order = same state
   * @param {Array} events - Events to project
   * @param {Object} [initialState] - Starting state
   * @returns {Object} Projected state
   */
  project(events, initialState = null) {
    let state = initialState || createInitialState();
    
    for (const event of events) {
      state = this.applyEvent(state, event);
      this._lastEventId = event.event_id;
      this._lastSequence = event.sequence;
    }
    
    this._state = state;
    return state;
  },

  /**
   * Rebuild state from Event Store (from scratch)
   * Uses sequence ordering for determinism
   * @param {Object} eventStore - EventStore instance
   * @returns {Object} Rebuilt state
   */
  rebuild(eventStore) {
    // Get all events ordered by sequence (deterministic)
    const { events } = eventStore.getEvents({ 
      limit: 100000, // Reasonable max
      orderBy: 'sequence'
    });
    
    // Reset internal state
    this._state = createInitialState();
    this._lastEventId = null;
    this._lastSequence = null;
    
    // Project all events
    return this.project(events, this._state);
  },

  /**
   * Incremental update from last known position
   * @param {Array} newEvents - New events since last projection
   * @returns {Object} Updated state
   */
  incrementalUpdate(newEvents) {
    if (!this._state) {
      throw new Error('State not initialized. Call rebuild() or project() first.');
    }
    
    // Sort by sequence to ensure deterministic order
    const sortedEvents = [...newEvents].sort((a, b) => 
      (a.sequence || 0) - (b.sequence || 0)
    );
    
    return this.project(sortedEvents, this._state);
  },

  /**
   * Get current cached state
   * Returns initial state if not yet projected
   * @returns {Object} Current state (never null)
   */
  getCurrentState() {
    if (!this._state) {
      this._state = createInitialState();
    }
    return deepClone(this._state);
  },

  /**
   * Get last processed event info
   * @returns {Object} { event_id, sequence }
   */
  getLastPosition() {
    return {
      event_id: this._lastEventId,
      sequence: this._lastSequence
    };
  },

  /**
   * Reset cached state (for testing)
   */
  reset() {
    this._state = null;
    this._lastEventId = null;
    this._lastSequence = null;
  }
};

/**
 * Create initial empty state
 * @returns {Object} Initial state structure
 */
function createInitialState() {
  return {
    // Meta
    projection_version: '2.0.0',
    projected_at: new Date().toISOString(),
    
    // Run data
    current_run: null,
    
    // Trading data
    open_positions: [],
    pending_orders: [],
    recent_signals: [],
    recent_intents: [],
    
    // Health
    current_health: null,
    
    // Config
    active_config: null,
    
    // Aggregates
    stats: {
      total_trades_today: 0,
      total_pnl_today: 0,
      max_drawdown_today: 0,
      uptime_seconds: 0
    },
    
    // Safety/Observability
    safety: {
      overall_status: 'healthy',
      active_violations: [],
      last_violation_at: null,
      block_trading: false
    },
    
    observability: {
      overall_status: 'healthy',
      active_warnings: [],
      last_report_attempt_at: null,
      last_successful_report_at: null,
      metrics: {
        reports_attempted: 0,
        reports_succeeded: 0,
        reports_failed: 0
      }
    }
  };
}

/**
 * Deep clone helper (side-effect-free)
 * @param {*} obj - Object to clone
 * @returns {*} Cloned object
 */
function deepClone(obj) {
  if (obj === null || typeof obj !== 'object') return obj;
  if (obj instanceof Date) return new Date(obj.getTime());
  if (Array.isArray(obj)) return obj.map(deepClone);
  
  const cloned = {};
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      cloned[key] = deepClone(obj[key]);
    }
  }
  return cloned;
}

module.exports = StateProjection;
