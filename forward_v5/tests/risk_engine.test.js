/**
 * Risk Engine Tests
 * Block 3: Core Reliability
 * 
 * Six Gates: Sizing, Hyperliquid, Whitelist, Watchdog, Reconcile, Unmanaged
 * Test-first: min 3 Tests pro Gate
 */

const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert');

const RiskEngine = require('../src/risk_engine.js');

describe('RiskEngine', () => {
  
  beforeEach(() => {
    RiskEngine.reset();
    RiskEngine.init({
      maxPositionSize: 10.0,
      maxLeverage: 10,
      maxPositionValueUSD: 100000,
      minNotionalUSD: 10,
      allowedSymbols: ['BTC', 'ETH', 'SOL'],
      symbolWhitelist: ['BTC', 'ETH'],
      maxTickAgeMs: 60000,
      maxHeartbeatAgeMs: 300000,
      maxDivergenceBps: 10
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GATE 1: SIZING
  // ═══════════════════════════════════════════════════════════
  describe('3.1 Sizing Gate (SAFETY → BLOCK)', () => {
    
    it('sizing_passes_when_under_limits', () => {
      const input = {
        positionSize: 5.0,
        leverage: 5,
        notionalValue: 50000,
        symbol: 'BTC-PERP'
      };
      
      const decisions = RiskEngine.checkGate('sizing', input);
      
      assert.strictEqual(decisions.length, 1);
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('sizing_blocks_oversized_position', () => {
      const input = {
        positionSize: 15.0,
        leverage: 5,
        notionalValue: 50000,
        symbol: 'BTC-PERP'
      };
      
      const decisions = RiskEngine.checkGate('sizing', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('Position size')));
    });

    it('sizing_blocks_excessive_leverage', () => {
      const input = {
        positionSize: 1.0,
        leverage: 15,
        notionalValue: 10000,
        symbol: 'BTC-PERP'
      };
      
      const decisions = RiskEngine.checkGate('sizing', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('Leverage')));
    });

    it('sizing_blocks_over_notional', () => {
      const input = {
        positionSize: 1.0,
        leverage: 1,
        notionalValue: 150000,
        symbol: 'BTC-PERP'
      };
      
      const decisions = RiskEngine.checkGate('sizing', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('Notional')));
    });

    it('sizing_multiple_violations_all_reported', () => {
      const input = {
        positionSize: 20.0,
        leverage: 20,
        notionalValue: 200000,
        symbol: 'BTC-PERP'
      };
      
      const decisions = RiskEngine.checkGate('sizing', input);
      const blocks = decisions.filter(d => d.level === 'BLOCK');
      
      assert.strictEqual(blocks.length, 3);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GATE 2: HYPERLIQUID RULES
  // ═══════════════════════════════════════════════════════════
  describe('3.2 Hyperliquid Rules Gate (SAFETY → BLOCK)', () => {
    
    it('hyperliquid_passes_valid_symbol', () => {
      const input = {
        symbol: 'BTC-PERP',
        notionalValue: 100
      };
      
      const decisions = RiskEngine.checkGate('hyperliquidRules', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('hyperliquid_blocks_below_min_notional', () => {
      const input = {
        symbol: 'BTC-PERP',
        notionalValue: 5
      };
      
      const decisions = RiskEngine.checkGate('hyperliquidRules', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('min')));
    });

    it('hyperliquid_blocks_unsupported_symbol', () => {
      const input = {
        symbol: 'XYZ-PERP',
        notionalValue: 1000
      };
      
      const decisions = RiskEngine.checkGate('hyperliquidRules', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('not available')));
    });

    it('hyperliquid_blocks_invalid_format', () => {
      const input = {
        symbol: 'BTC/USD', // Wrong separator
        notionalValue: 100
      };
      
      const decisions = RiskEngine.checkGate('hyperliquidRules', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('format')));
    });

    it('hyperliquid_accepts_spot_format', () => {
      const input = {
        symbol: 'BTC-USD',
        notionalValue: 100
      };
      
      const decisions = RiskEngine.checkGate('hyperliquidRules', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('hyperliquid_accepts_perp_format', () => {
      const input = {
        symbol: 'ETH-PERP',
        notionalValue: 100
      };
      
      const decisions = RiskEngine.checkGate('hyperliquidRules', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GATE 3: SYMBOL WHITELIST
  // ═══════════════════════════════════════════════════════════
  describe('3.3 Symbol Whitelist Gate (SAFETY → BLOCK)', () => {
    
    it('whitelist_passes_allowed_symbol', () => {
      const input = {
        symbol: 'BTC-PERP'
      };
      
      const decisions = RiskEngine.checkGate('symbolWhitelist', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('whitelist_blocks_disallowed_symbol', () => {
      const input = {
        symbol: 'SOL-PERP' // Not in whitelist
      };
      
      const decisions = RiskEngine.checkGate('symbolWhitelist', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('whitelist')));
    });

    it('whitelist_disabled_when_null', () => {
      RiskEngine.init({ symbolWhitelist: null });
      
      const input = {
        symbol: 'ANY-PERP'
      };
      
      const decisions = RiskEngine.checkGate('symbolWhitelist', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('whitelist_disabled_when_empty', () => {
      RiskEngine.init({ symbolWhitelist: [] });
      
      const input = {
        symbol: 'ANY-PERP'
      };
      
      const decisions = RiskEngine.checkGate('symbolWhitelist', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('whitelist_extracts_base_symbol', () => {
      const input = {
        symbol: 'BTC-PERP' // Should extract BTC
      };
      
      const decisions = RiskEngine.checkGate('symbolWhitelist', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GATE 4: WATCHDOG (NEVER BLOCK)
  // ═══════════════════════════════════════════════════════════
  describe('3.4 Watchdog Gate (OBSERVABILITY → WARN only)', () => {
    
    it('watchdog_passes_when_fresh', () => {
      const now = Date.now();
      const input = {
        lastTickAt: new Date(now - 10000).toISOString(),
        lastHeartbeatAt: new Date(now - 10000).toISOString(),
        currentTime: now
      };
      
      const decisions = RiskEngine.checkGate('watchdog', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('watchdog_warns_stale_tick', () => {
      const now = Date.now();
      const input = {
        lastTickAt: new Date(now - 120000).toISOString(), // 2 min ago
        lastHeartbeatAt: new Date(now - 10000).toISOString(),
        currentTime: now
      };
      
      const decisions = RiskEngine.checkGate('watchdog', input);
      
      assert.ok(decisions.some(d => d.level === 'WARN'));
      assert.ok(decisions.some(d => d.reason.includes('tick')));
      // NEVER BLOCK
      assert.ok(!decisions.some(d => d.level === 'BLOCK'));
    });

    it('watchdog_warns_stale_heartbeat', () => {
      const now = Date.now();
      const input = {
        lastTickAt: new Date(now - 10000).toISOString(),
        lastHeartbeatAt: new Date(now - 400000).toISOString(), // 6 min ago
        currentTime: now
      };
      
      const decisions = RiskEngine.checkGate('watchdog', input);
      
      assert.ok(decisions.some(d => d.level === 'WARN'));
      assert.ok(decisions.some(d => d.reason.includes('heartbeat')));
      assert.ok(!decisions.some(d => d.level === 'BLOCK'));
    });

    it('watchdog_both_stale_multiple_warnings', () => {
      const now = Date.now();
      const input = {
        lastTickAt: new Date(now - 120000).toISOString(),
        lastHeartbeatAt: new Date(now - 400000).toISOString(),
        currentTime: now
      };
      
      const decisions = RiskEngine.checkGate('watchdog', input);
      const warns = decisions.filter(d => d.level === 'WARN');
      
      assert.strictEqual(warns.length, 2);
    });

    it('watchdog_never_blocks_even_extreme_staleness', () => {
      const now = Date.now();
      const input = {
        lastTickAt: new Date(now - 3600000).toISOString(), // 1 hour ago
        lastHeartbeatAt: new Date(now - 3600000).toISOString(),
        currentTime: now
      };
      
      const decisions = RiskEngine.checkGate('watchdog', input);
      
      // Should warn but NEVER block
      assert.ok(decisions.some(d => d.level === 'WARN'));
      assert.ok(!decisions.some(d => d.level === 'BLOCK'));
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GATE 5: RECONCILE (SAFETY → BLOCK)
  // ═══════════════════════════════════════════════════════════
  describe('3.5 Reconcile Gate (SAFETY → BLOCK)', () => {
    
    it('reconcile_passes_when_match', () => {
      const input = {
        internalPositions: [
          { symbol: 'BTC-PERP', size: 1.0 }
        ],
        exchangePositions: [
          { symbol: 'BTC-PERP', size: 1.0 }
        ]
      };
      
      const decisions = RiskEngine.checkGate('reconcile', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('reconcile_blocks_phantom_position', () => {
      const input = {
        internalPositions: [
          { symbol: 'BTC-PERP', size: 1.0 }
        ],
        exchangePositions: [] // Missing on exchange
      };
      
      const decisions = RiskEngine.checkGate('reconcile', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('exists internally')));
    });

    it('reconcile_blocks_size_divergence', () => {
      const input = {
        internalPositions: [
          { symbol: 'BTC-PERP', size: 1.0 }
        ],
        exchangePositions: [
          { symbol: 'BTC-PERP', size: 1.5 } // Different size
        ]
      };
      
      const decisions = RiskEngine.checkGate('reconcile', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('divergence')));
    });

    it('reconcile_blocks_unknown_exchange_position', () => {
      const input = {
        internalPositions: [],
        exchangePositions: [
          { symbol: 'ETH-PERP', size: 2.0 } // Unknown to us
        ]
      };
      
      const decisions = RiskEngine.checkGate('reconcile', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('Unknown')));
    });

    it('reconcile_tolerates_minor_divergence', () => {
      // 5 bps is within 10 bps limit
      const input = {
        internalPositions: [
          { symbol: 'BTC-PERP', size: 1.0000 }
        ],
        exchangePositions: [
          { symbol: 'BTC-PERP', size: 1.0005 } // ~5 bps
        ]
      };
      
      const decisions = RiskEngine.checkGate('reconcile', input);
      
      // Should pass - divergence is small
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('reconcile_reports_multiple_divergences', () => {
      const input = {
        internalPositions: [
          { symbol: 'BTC-PERP', size: 1.0 },
          { symbol: 'ETH-PERP', size: 2.0 }
        ],
        exchangePositions: [
          { symbol: 'BTC-PERP', size: 1.5 },
          { symbol: 'ETH-PERP', size: 2.5 }
        ]
      };
      
      const decisions = RiskEngine.checkGate('reconcile', input);
      const blocks = decisions.filter(d => d.level === 'BLOCK');
      
      assert.strictEqual(blocks.length, 2);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GATE 6: UNMANAGED POSITION (SAFETY → BLOCK/WARN)
  // ═══════════════════════════════════════════════════════════
  describe('3.6 Unmanaged Position Gate (SAFETY → BLOCK/WARN)', () => {
    
    it('unmanaged_passes_all_known', () => {
      const input = {
        knownPositionIds: ['pos_1', 'pos_2'],
        currentPositions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0 },
          { position_id: 'pos_2', symbol: 'ETH-PERP', size: 2.0 }
        ]
      };
      
      const decisions = RiskEngine.checkGate('unmanagedPosition', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });

    it('unmanaged_blocks_unknown_in_strict_mode', () => {
      const input = {
        knownPositionIds: ['pos_1'],
        currentPositions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0 },
          { position_id: 'pos_999', symbol: 'ETH-PERP', size: 2.0 } // Unknown
        ],
        strict: true
      };
      
      const decisions = RiskEngine.checkGate('unmanagedPosition', input);
      
      assert.ok(decisions.some(d => d.level === 'BLOCK'));
      assert.ok(decisions.some(d => d.reason.includes('not opened by system')));
    });

    it('unmanaged_warns_unknown_in_non_strict_mode', () => {
      const input = {
        knownPositionIds: ['pos_1'],
        currentPositions: [
          { position_id: 'pos_999', symbol: 'ETH-PERP', size: 2.0 }
        ],
        strict: false
      };
      
      const decisions = RiskEngine.checkGate('unmanagedPosition', input);
      
      // Should warn, not block
      assert.ok(decisions.some(d => d.level === 'WARN'));
      assert.ok(!decisions.some(d => d.level === 'BLOCK'));
    });

    it('unmanaged_reports_multiple_unknown', () => {
      const input = {
        knownPositionIds: [],
        currentPositions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0 },
          { position_id: 'pos_2', symbol: 'ETH-PERP', size: 2.0 },
          { position_id: 'pos_3', symbol: 'SOL-PERP', size: 3.0 }
        ],
        strict: true
      };
      
      const decisions = RiskEngine.checkGate('unmanagedPosition', input);
      const blocks = decisions.filter(d => d.level === 'BLOCK');
      
      assert.strictEqual(blocks.length, 3);
    });

    it('unmanaged_empty_positions_pass', () => {
      const input = {
        knownPositionIds: [],
        currentPositions: [],
        strict: true
      };
      
      const decisions = RiskEngine.checkGate('unmanagedPosition', input);
      
      assert.strictEqual(decisions[0].level, 'PASS');
    });
  });

  // ═══════════════════════════════════════════════════════════
  // INTEGRATION: checkAll()
  // ═══════════════════════════════════════════════════════════
  describe('3.7 Integration: checkAll()', () => {
    
    it('checkAll_passes_clean_input', () => {
      const input = {
        positionSize: 1.0,
        leverage: 5,
        notionalValue: 1000,
        symbol: 'BTC-PERP',
        internalPositions: [],
        exchangePositions: [],
        knownPositionIds: [],
        currentPositions: [],
        lastTickAt: new Date().toISOString(),
        lastHeartbeatAt: new Date().toISOString(),
        currentTime: Date.now()
      };
      
      const result = RiskEngine.checkAll(input);
      
      assert.strictEqual(result.passed, true);
      assert.strictEqual(result.blocked, false);
    });

    it('checkAll_blocks_with_events', () => {
      const input = {
        positionSize: 20.0, // Too large
        leverage: 5,
        notionalValue: 5, // Below min
        symbol: 'XYZ-PERP', // Not supported
        internalPositions: [],
        exchangePositions: [],
        knownPositionIds: [],
        currentPositions: [],
        lastTickAt: new Date().toISOString(),
        lastHeartbeatAt: new Date().toISOString()
      };
      
      const result = RiskEngine.checkAll(input);
      
      assert.strictEqual(result.passed, false);
      assert.strictEqual(result.blocked, true);
      assert.ok(result.blockReason);
      assert.ok(result.events.length > 0);
      
      // Events should be SAFETY_VIOLATED
      const safetyEvents = result.events.filter(e => e.event_type === 'SAFETY_VIOLATED');
      assert.ok(safetyEvents.length > 0);
    });

    it('checkAll_generates_observability_warnings', () => {
      const now = Date.now();
      const input = {
        positionSize: 1.0,
        leverage: 5,
        notionalValue: 1000,
        symbol: 'BTC-PERP',
        internalPositions: [],
        exchangePositions: [],
        knownPositionIds: [],
        currentPositions: [],
        lastTickAt: new Date(now - 120000).toISOString(), // Stale
        lastHeartbeatAt: new Date(now - 400000).toISOString(), // Stale
        currentTime: now
      };
      
      const result = RiskEngine.checkAll(input);
      
      // Should pass (not blocked) but have warnings
      assert.strictEqual(result.passed, true);
      assert.strictEqual(result.warnings, 2);
      
      // Events should be OBSERVABILITY_WARN
      const obsEvents = result.events.filter(e => e.event_type === 'OBSERVABILITY_WARN');
      assert.strictEqual(obsEvents.length, 2);
    });

    it('checkAll_never_blocks_on_watchdog', () => {
      const now = Date.now();
      const input = {
        positionSize: 1.0, // Valid
        leverage: 1,
        notionalValue: 1000,
        symbol: 'BTC-PERP', // Valid
        internalPositions: [],
        exchangePositions: [],
        knownPositionIds: [],
        currentPositions: [],
        lastTickAt: new Date(now - 3600000).toISOString(), // 1 hour stale
        lastHeartbeatAt: new Date(now - 3600000).toISOString(),
        currentTime: now
      };
      
      const result = RiskEngine.checkAll(input);
      
      // Should NOT block even with extreme staleness
      assert.strictEqual(result.passed, true);
      assert.strictEqual(result.blocked, false);
      assert.ok(result.warnings > 0);
    });

    it('checkAll_includes_timestamp', () => {
      const input = {
        positionSize: 1.0,
        leverage: 1,
        notionalValue: 1000,
        symbol: 'BTC-PERP',
        internalPositions: [],
        exchangePositions: [],
        knownPositionIds: [],
        currentPositions: [],
        lastTickAt: new Date().toISOString(),
        lastHeartbeatAt: new Date().toISOString()
      };
      
      const result = RiskEngine.checkAll(input);
      
      assert.ok(result.timestamp);
      assert.ok(new Date(result.timestamp).getTime() > 0);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // DETERMINISM
  // ═══════════════════════════════════════════════════════════
  describe('3.8 Determinism', () => {
    
    it('same_input_same_output', () => {
      const input = {
        positionSize: 15.0, // Should BLOCK
        leverage: 5,
        notionalValue: 1000,
        symbol: 'BTC-PERP'
      };
      
      const result1 = RiskEngine.checkGate('sizing', input);
      const result2 = RiskEngine.checkGate('sizing', input);
      
      assert.deepStrictEqual(result1, result2);
    });

    it('no_side_effects', () => {
      const input = {
        // Input at limit boundary - should PASS
        positionSize: 10.0,
        leverage: 10,
        notionalValue: 100000
      };
      
      // Same input multiple times
      RiskEngine.checkGate('sizing', input);
      RiskEngine.checkGate('sizing', input);
      const result = RiskEngine.checkGate('sizing', input);
      
      // Should return consistent result (PASS)
      assert.strictEqual(result.length, 1);
      assert.strictEqual(result[0].level, 'PASS');
    });
  });
});
