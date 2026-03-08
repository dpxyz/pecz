/**
 * Risk Engine
 * Block 3: Core Reliability
 * 
 * Six Gates für Safety und Observability.
 * PURE FUNCTIONS - keine Seiteneffekte.
 * HYPERLIQUID ONLY - Paper/Mock Mode.
 */

const RiskEngine = {
  // Configuration (injected, immutable)
  _config: null,
  
  /**
   * Initialize with risk configuration
   * @param {Object} config - Risk limits and rules
   */
  init(config = {}) {
    this._config = {
      // Sizing
      maxPositionSize: config.maxPositionSize || 10.0,
      maxLeverage: config.maxLeverage || 10,
      maxPositionValueUSD: config.maxPositionValueUSD || 100000,
      
      // Hyperliquid
      minNotionalUSD: config.minNotionalUSD || 10,
      allowedSymbols: config.allowedSymbols || [
        'BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'UNI', 'AAVE', 'CRV'
      ],
      
      // Symbol Whitelist
      symbolWhitelist: config.symbolWhitelist || null, // null = all allowed
      
      // Watchdog
      maxTickAgeMs: config.maxTickAgeMs || 60000,
      maxHeartbeatAgeMs: config.maxHeartbeatAgeMs || 300000,
      
      // Reconcile
      maxDivergenceBps: config.maxDivergenceBps || 10,
      
      // Unmanaged
      strictUnmanagedCheck: config.strictUnmanagedCheck ?? true,
      
      ...config
    };
    
    return this;
  },

  /**
   * Check a single gate
   * Returns decision object - NO side effects
   */
  gates: {
    /**
     * Sizing Gate: Position size and leverage limits
     * SAFETY GATE → can BLOCK
     */
    sizing: (input, config) => {
      const { positionSize, leverage, notionalValue, symbol } = input;
      const decisions = [];
      
      if (positionSize > config.maxPositionSize) {
        decisions.push({
          gate: 'sizing',
          level: 'BLOCK',
          reason: `Position size ${positionSize} exceeds max ${config.maxPositionSize}`,
          metric: { name: 'position_size', value: positionSize, limit: config.maxPositionSize }
        });
      }
      
      if (leverage > config.maxLeverage) {
        decisions.push({
          gate: 'sizing',
          level: 'BLOCK',
          reason: `Leverage ${leverage}x exceeds max ${config.maxLeverage}x`,
          metric: { name: 'leverage', value: leverage, limit: config.maxLeverage }
        });
      }
      
      if (notionalValue > config.maxPositionValueUSD) {
        decisions.push({
          gate: 'sizing',
          level: 'BLOCK',
          reason: `Notional ${notionalValue} exceeds max ${config.maxPositionValueUSD}`,
          metric: { name: 'notional_value', value: notionalValue, limit: config.maxPositionValueUSD }
        });
      }
      
      return decisions.length > 0 ? decisions : [{ gate: 'sizing', level: 'PASS' }];
    },

    /**
     * Hyperliquid Rules Gate: Exchange-specific constraints
     * SAFETY GATE → can BLOCK
     */
    hyperliquidRules: (input, config) => {
      const { symbol, notionalValue } = input;
      const decisions = [];
      
      // Check min notional
      if (notionalValue < config.minNotionalUSD) {
        decisions.push({
          gate: 'hyperliquid_rules',
          level: 'BLOCK',
          reason: `Notional ${notionalValue} below Hyperliquid min ${config.minNotionalUSD}`,
          metric: { name: 'min_notional', value: notionalValue, limit: config.minNotionalUSD }
        });
      }
      
      // Check if symbol is valid on Hyperliquid
      // Hyperliquid spot: BTC, ETH, SOL, etc.
      // Hyperliquid perp: BTC-PERP, ETH-PERP, etc.
      const baseSymbol = symbol.replace(/-PERP$|-USD$/, '');
      if (!config.allowedSymbols.includes(baseSymbol)) {
        decisions.push({
          gate: 'hyperliquid_rules',
          level: 'BLOCK',
          reason: `Symbol ${symbol} not available on Hyperliquid`,
          metric: { name: 'symbol_validity', symbol: baseSymbol }
        });
      }
      
      // Check if spot vs perp is valid
      if (symbol.includes('-PERP')) {
        // Perpetuals are supported
      } else if (!symbol.match(/^[A-Z]+-USD$/)) {
        decisions.push({
          gate: 'hyperliquid_rules',
          level: 'BLOCK',
          reason: `Invalid Hyperliquid symbol format: ${symbol}`,
          metric: { name: 'symbol_format', symbol }
        });
      }
      
      return decisions.length > 0 ? decisions : [{ gate: 'hyperliquid_rules', level: 'PASS' }];
    },

    /**
     * Symbol Whitelist Gate: Only trade specified symbols
     * SAFETY GATE → can BLOCK
     */
    symbolWhitelist: (input, config) => {
      if (!config.symbolWhitelist || config.symbolWhitelist.length === 0) {
        // Whitelist disabled
        return [{ gate: 'symbol_whitelist', level: 'PASS' }];
      }
      
      const { symbol } = input;
      const baseSymbol = symbol.replace(/-PERP$/, '');
      
      if (!config.symbolWhitelist.includes(baseSymbol)) {
        return [{
          gate: 'symbol_whitelist',
          level: 'BLOCK',
          reason: `Symbol ${symbol} not in whitelist`,
          metric: { name: 'symbol_whitelist', symbol: baseSymbol }
        }];
      }
      
      return [{ gate: 'symbol_whitelist', level: 'PASS' }];
    },

    /**
     * Watchdog Gate: Health checks - NEVER BLOCK
     * OBSERVABILITY GATE → only WARN
     */
    watchdog: (input, config) => {
      const { lastTickAt, lastHeartbeatAt, currentTime } = input;
      const decisions = [];
      const now = currentTime || Date.now();
      
      // Check tick age
      if (lastTickAt) {
        const tickAge = now - new Date(lastTickAt).getTime();
        if (tickAge > config.maxTickAgeMs) {
          decisions.push({
            gate: 'watchdog',
            level: 'WARN',
            reason: `Last tick ${tickAge}ms ago exceeds max ${config.maxTickAgeMs}ms`,
            metric: { name: 'tick_age_ms', value: tickAge, limit: config.maxTickAgeMs }
          });
        }
      }
      
      // Check heartbeat age
      if (lastHeartbeatAt) {
        const heartbeatAge = now - new Date(lastHeartbeatAt).getTime();
        if (heartbeatAge > config.maxHeartbeatAgeMs) {
          decisions.push({
            gate: 'watchdog',
            level: 'WARN',
            reason: `Last heartbeat ${heartbeatAge}ms ago exceeds max ${config.maxHeartbeatAgeMs}ms`,
            metric: { name: 'heartbeat_age_ms', value: heartbeatAge, limit: config.maxHeartbeatAgeMs }
          });
        }
      }
      
      return decisions.length > 0 ? decisions : [{ gate: 'watchdog', level: 'PASS' }];
    },

    /**
     * Reconcile Gate: Internal state vs Hyperliquid
     * SAFETY GATE → can BLOCK
     */
    reconcile: (input, config) => {
      const { internalPositions, exchangePositions } = input;
      const decisions = [];
      
      // Map internal positions by symbol
      const internalBySymbol = new Map();
      for (const pos of internalPositions || []) {
        internalBySymbol.set(pos.symbol, pos);
      }
      
      // Map exchange positions by symbol
      const exchangeBySymbol = new Map();
      for (const pos of exchangePositions || []) {
        exchangeBySymbol.set(pos.symbol, pos);
      }
      
      // Check all internal positions exist on exchange
      for (const [symbol, internal] of internalBySymbol) {
        const exchange = exchangeBySymbol.get(symbol);
        
        if (!exchange) {
          // Internal shows position but exchange doesn't
          decisions.push({
            gate: 'reconcile',
            level: 'BLOCK',
            reason: `Position ${symbol} exists internally but not on Hyperliquid`,
            metric: { name: 'phantom_position', symbol, internal_size: internal.size }
          });
        } else {
          // Compare sizes
          const sizeDiff = Math.abs(internal.size - exchange.size);
          const diffBps = (sizeDiff / Math.max(internal.size, exchange.size)) * 10000;
          
          if (diffBps > config.maxDivergenceBps) {
            decisions.push({
              gate: 'reconcile',
              level: 'BLOCK',
              reason: `Position ${symbol} divergence ${diffBps.toFixed(0)} bps exceeds max ${config.maxDivergenceBps} bps`,
              metric: { 
                name: 'size_divergence', 
                symbol, 
                internal: internal.size, 
                exchange: exchange.size, 
                divergence_bps: diffBps 
              }
            });
          }
        }
      }
      
      // Check for unknown positions on exchange
      for (const [symbol, exchange] of exchangeBySymbol) {
        if (!internalBySymbol.has(symbol)) {
          // Exchange has position we don't know about
          decisions.push({
            gate: 'reconcile',
            level: 'BLOCK',
            reason: `Unknown position ${symbol} exists on Hyperliquid`,
            metric: { name: 'unmanaged_position', symbol, size: exchange.size }
          });
        }
      }
      
      return decisions.length > 0 ? decisions : [{ gate: 'reconcile', level: 'PASS' }];
    },

    /**
     * Unmanaged Position Gate: Positions not opened by our system
     * SAFETY GATE → can BLOCK
     */
    unmanagedPosition: (input, config) => {
      const { knownPositionIds, currentPositions, strict } = input;
      const strictMode = strict ?? config.strictUnmanagedCheck;
      const decisions = [];
      
      for (const position of currentPositions || []) {
        const isKnown = (knownPositionIds || []).includes(position.position_id);
        
        if (!isKnown) {
          if (strictMode) {
            decisions.push({
              gate: 'unmanaged_position',
              level: 'BLOCK',
              reason: `Unknown position ${position.position_id} detected - not opened by system`,
              metric: { 
                name: 'unmanaged_position',
                position_id: position.position_id,
                symbol: position.symbol,
                size: position.size
              }
            });
          } else {
            decisions.push({
              gate: 'unmanaged_position',
              level: 'WARN',
              reason: `Unknown position ${position.position_id} detected (non-strict mode)`,
              metric: { 
                name: 'unmanaged_position',
                position_id: position.position_id,
                symbol: position.symbol
              }
            });
          }
        }
      }
      
      return decisions.length > 0 ? decisions : [{ gate: 'unmanaged_position', level: 'PASS' }];
    }
  },

  /**
   * Run all gates and generate events
   * @param {Object} input - Combined input for all gates
   * @returns {Object} { passed: Boolean, events: [], blockReason: String }
   */
  checkAll(input) {
    if (!this._config) {
      this.init({});
    }
    
    const events = [];
    let blocked = false;
    let blockReason = null;
    let warnings = 0;
    
    // Run each gate
    const gates = [
      'sizing',
      'hyperliquidRules', 
      'symbolWhitelist',
      'watchdog',
      'reconcile',
      'unmanagedPosition'
    ];
    
    for (const gateName of gates) {
      const gateFn = this.gates[gateName];
      const gateInput = this._extractGateInput(gateName, input);
      const decisions = gateFn(gateInput, this._config);
      
      for (const decision of decisions) {
        if (decision.level === 'BLOCK') {
          blocked = true;
          blockReason = decision.reason;
          events.push({
            event_type: 'SAFETY_VIOLATED',
            payload: {
              gate: decision.gate,
              severity: 'block',
              message: decision.reason,
              metric: decision.metric,
              timestamp: new Date().toISOString()
            }
          });
        } else if (decision.level === 'WARN') {
          warnings++;
          events.push({
            event_type: 'OBSERVABILITY_WARN',
            payload: {
              gate: decision.gate,
              severity: 'warn',
              message: decision.reason,
              metric: decision.metric,
              timestamp: new Date().toISOString()
            }
          });
        }
      }
    }
    
    return {
      passed: !blocked,
      blocked,
      blockReason,
      warnings,
      events,
      timestamp: new Date().toISOString()
    };
  },

  /**
   * Extract relevant input for each gate
   */
  _extractGateInput(gateName, fullInput) {
    // Most gates use common fields, but we might expand this
    return fullInput;
  },

  /**
   * Check a single gate (for testing)
   */
  checkGate(gateName, input) {
    if (!this._config) this.init({});
    const gateFn = this.gates[gateName];
    return gateFn(input, this._config);
  },

  /**
   * Reset for testing
   */
  reset() {
    this._config = null;
  }
};

module.exports = RiskEngine;
