/**
 * Reconcile Engine Tests
 * Block 4: Core Reliability
 * 
 * Position comparison: Internal State vs External Snapshot
 * Mismatches: Ghost, Unmanaged, Size, Side
 */

const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert');
const ReconcileEngine = require('../src/reconcile.js');

describe('ReconcileEngine', () => {
  
  beforeEach(() => {
    ReconcileEngine.reset();
    ReconcileEngine.init({
      sizeToleranceBps: 10,        // 0.1%
      sideMismatchIsBlock: true,   // Always BLOCK
      unmanagedIsBlock: true       // Always BLOCK
    });
  });

  // ═══════════════════════════════════════════════════════════
  // GHOST POSITION DETECTOR
  // ═══════════════════════════════════════════════════════════
  describe('4.1 Ghost Position Detector', () => {
    
    it('ghost_detects_internal_without_external', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }
        ]
      };
      const externalSnapshot = { positions: [] };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      assert.strictEqual(result.blocked, true);
      assert.ok(result.findings.some(f => f.type === 'GHOST_POSITION'));
      assert.ok(result.events.some(e => e.payload.mismatch_type === 'GHOST_POSITION'));
    });

    it('ghost_no_false_positive_when_match', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }
        ]
      };
      const externalSnapshot = {
        positions: [
          { symbol: 'BTC-PERP', size: 1.0, side: 'long' }
        ]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const ghosts = result.findings.filter(f => f.type === 'GHOST_POSITION');
      
      assert.strictEqual(ghosts.length, 0);
    });

    it('ghost_reports_position_details', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'ETH-PERP', size: 5.0, side: 'short' }
        ]
      };
      const externalSnapshot = { positions: [] };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const ghost = result.findings.find(f => f.type === 'GHOST_POSITION');
      
      assert.strictEqual(ghost.severity, 'BLOCK');
      assert.strictEqual(ghost.symbol, 'ETH-PERP');
      assert.strictEqual(ghost.internal.size, 5.0);
      assert.strictEqual(ghost.internal.side, 'short');
    });

    it('ghost_detects_multiple_ghosts', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' },
          { position_id: 'pos_2', symbol: 'ETH-PERP', size: 2.0, side: 'long' },
          { position_id: 'pos_3', symbol: 'SOL-PERP', size: 3.0, side: 'long' }
        ]
      };
      const externalSnapshot = { positions: [] };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const ghosts = result.findings.filter(f => f.type === 'GHOST_POSITION');
      
      assert.strictEqual(ghosts.length, 3);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // UNMANAGED POSITION DETECTOR
  // ═══════════════════════════════════════════════════════════
  describe('4.2 Unmanaged Position Detector', () => {
    
    it('unmanaged_detects_external_without_internal', () => {
      const internalState = { open_positions: [] };
      const externalSnapshot = {
        positions: [
          { symbol: 'BTC-PERP', size: 1.0, side: 'long' }
        ]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      assert.strictEqual(result.blocked, true);
      assert.ok(result.findings.some(f => f.type === 'UNMANAGED_POSITION'));
    });

    it('unmanaged_severity_block_by_default', () => {
      const internalState = { open_positions: [] };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const unmanaged = result.findings.find(f => f.type === 'UNMANAGED_POSITION');
      
      assert.strictEqual(unmanaged.severity, 'BLOCK');
    });

    it('unmanaged_can_warn_in_lenient_mode', () => {
      ReconcileEngine.init({ unmanagedIsBlock: false });
      
      const internalState = { open_positions: [] };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      // Should NOT block in lenient mode
      assert.strictEqual(result.blocked, false);
      assert.strictEqual(result.passed, true);
      assert.ok(result.findings.some(f => f.type === 'UNMANAGED_POSITION' && f.severity === 'WARN'));
    });

    it('unmanaged_reports_size_and_symbol', () => {
      const internalState = { open_positions: [] };
      const externalSnapshot = {
        positions: [{ symbol: 'LINK-PERP', size: 100.0, side: 'short' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const unmanaged = result.findings.find(f => f.type === 'UNMANAGED_POSITION');
      
      assert.strictEqual(unmanaged.symbol, 'LINK-PERP');
      assert.strictEqual(unmanaged.external.size, 100.0);
      assert.strictEqual(unmanaged.external.side, 'short');
    });

    it('unmanaged_detects_multiple', () => {
      const internalState = { open_positions: [] };
      const externalSnapshot = {
        positions: [
          { symbol: 'BTC-PERP', size: 1.0, side: 'long' },
          { symbol: 'ETH-PERP', size: 2.0, side: 'long' },
          { symbol: 'SOL-PERP', size: 3.0, side: 'long' }
        ]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const unmanaged = result.findings.filter(f => f.type === 'UNMANAGED_POSITION');
      
      assert.strictEqual(unmanaged.length, 3);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // SIZE MISMATCH DETECTOR
  // ═══════════════════════════════════════════════════════════
  describe('4.3 Size Mismatch Detector', () => {
    
    it('size_blocks_when_above_tolerance', () => {
      // 1% diff > 0.1% tolerance → BLOCK
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.01, side: 'long' }] // 1% diff
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sizeMismatch = result.findings.find(f => f.type === 'SIZE_MISMATCH');
      
      assert.ok(sizeMismatch);
      assert.strictEqual(sizeMismatch.severity, 'BLOCK');
    });

    it('size_warns_when_within_tolerance', () => {
      // 0.05% diff < 0.1% tolerance → WARN
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0005, side: 'long' }] // 0.05% diff
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sizeMismatch = result.findings.find(f => f.type === 'SIZE_MISMATCH');
      
      assert.ok(sizeMismatch);
      assert.strictEqual(sizeMismatch.severity, 'WARN');
    });

    it('size_no_finding_when_exact_match', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sizeMismatches = result.findings.filter(f => f.type === 'SIZE_MISMATCH');
      
      assert.strictEqual(sizeMismatches.length, 0);
    });

    it('size_reports_bps_difference', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.02, side: 'long' }] // 2% diff
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sizeMismatch = result.findings.find(f => f.type === 'SIZE_MISMATCH');
      
      assert.ok(sizeMismatch.metric.diff_bps > 190); // ~200 bps
      assert.ok(sizeMismatch.metric.diff_bps < 210);
    });

    it('size_handles_zero_gracefully', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 0, side: 'long' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sizeMismatches = result.findings.filter(f => f.type === 'SIZE_MISMATCH');
      
      // Zero size match should not trigger
      assert.strictEqual(sizeMismatches.length, 0);
    });

    it('size_respects_configured_tolerance', () => {
      ReconcileEngine.init({ sizeToleranceBps: 50 }); // 0.5%
      
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.003, side: 'long' }] // 0.3% diff within 0.5%
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sizeMismatch = result.findings.find(f => f.type === 'SIZE_MISMATCH');
      
      assert.ok(sizeMismatch);
      assert.strictEqual(sizeMismatch.severity, 'WARN'); // Within new tolerance
    });
  });

  // ═══════════════════════════════════════════════════════════
  // SIDE MISMATCH DETECTOR
  // ═══════════════════════════════════════════════════════════
  describe('4.4 Side Mismatch Detector', () => {
    
    it('side_blocks_long_vs_short', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'short' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sideMismatch = result.findings.find(f => f.type === 'SIDE_MISMATCH');
      
      assert.ok(sideMismatch);
      assert.strictEqual(sideMismatch.severity, 'BLOCK');
    });

    it('side_no_findind_when_same_side', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sideMismatches = result.findings.filter(f => f.type === 'SIDE_MISMATCH');
      
      assert.strictEqual(sideMismatches.length, 0);
    });

    it('side_normalizes_variants', () => {
      // "buy" vs "long", "sell" vs "short"
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'buy' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sideMismatches = result.findings.filter(f => f.type === 'SIDE_MISMATCH');
      
      // Both should normalize to "long"
      assert.strictEqual(sideMismatches.length, 0);
    });

    it('side_reports_both_sides_in_explanation', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'ETH-PERP', size: 2.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'ETH-PERP', size: 2.0, side: 'short' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sideMismatch = result.findings.find(f => f.type === 'SIDE_MISMATCH');
      
      assert.ok(sideMismatch.explanation.includes('long'));
      assert.ok(sideMismatch.explanation.includes('short'));
    });

    it('side_can_warn_in_lenient_mode', () => {
      ReconcileEngine.init({ sideMismatchIsBlock: false });
      
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.0, side: 'short' }]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const sideMismatch = result.findings.find(f => f.type === 'SIDE_MISMATCH');
      
      assert.strictEqual(sideMismatch.severity, 'WARN');
      assert.strictEqual(result.blocked, false);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // INTEGRATION
  // ═══════════════════════════════════════════════════════════
  describe('4.5 Integration', () => {
    
    it('reconcile_handles_empty_states', () => {
      const result = ReconcileEngine.reconcile(
        { open_positions: [] },
        { positions: [] }
      );
      
      assert.strictEqual(result.passed, true);
      assert.strictEqual(result.totalFindings, 0);
      assert.strictEqual(result.blocked, false);
    });

    it('reconcile_detects_mixed_issues', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_ghost', symbol: 'BTC-PERP', size: 1.0, side: 'long' }, // Ghost
          { position_id: 'pos_size', symbol: 'ETH-PERP', size: 1.0, side: 'long' }   // Size mismatch
        ]
      };
      const externalSnapshot = {
        positions: [
          { symbol: 'ETH-PERP', size: 2.0, side: 'long' }, // Size mismatch
          { symbol: 'SOL-PERP', size: 3.0, side: 'long' }  // Unmanaged
        ]
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      assert.strictEqual(result.blocked, true);
      assert.ok(result.findings.some(f => f.type === 'GHOST_POSITION'));
      assert.ok(result.findings.some(f => f.type === 'UNMANAGED_POSITION'));
      assert.ok(result.findings.some(f => f.type === 'SIZE_MISMATCH'));
    });

    it('reconcile_generates_correct_event_types', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }
        ]
      };
      const externalSnapshot = { positions: [] };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      assert.ok(result.events.length > 0);
      assert.ok(result.events.every(e => e.event_type === 'RECONCILE_MISMATCH'));
      assert.ok(result.events.every(e => e.payload.timestamp));
    });

    it('events_include_all_necessary_fields', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }
        ]
      };
      const externalSnapshot = { positions: [] };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const event = result.events[0];
      
      assert.ok(event.payload.mismatch_type);
      assert.ok(event.payload.severity);
      assert.ok(event.payload.symbol);
      assert.ok(event.payload.explanation);
      assert.ok(event.payload.internal_snapshot !== undefined);
      assert.ok(event.payload.external_snapshot !== undefined);
      assert.ok(event.payload.metric);
      assert.ok(event.payload.timestamp);
    });

    it('passed_true_when_only_warnings', () => {
      // Small size drift (within tolerance) → WARN, not BLOCK
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = {
        positions: [{ symbol: 'BTC-PERP', size: 1.00005, side: 'long' }] // Tiny drift
      };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      assert.strictEqual(result.blocked, false);
      assert.strictEqual(result.passed, true);
      assert.strictEqual(result.warningCount > 0, true);
    });

    it('isReconciled_returns_boolean', () => {
      const clean = ReconcileEngine.isReconciled(
        { open_positions: [] },
        { positions: [] }
      );
      assert.strictEqual(clean, true);
      
      const dirty = ReconcileEngine.isReconciled(
        { open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }] },
        { positions: [] }
      );
      assert.strictEqual(dirty, false);
    });
  });

  // ═══════════════════════════════════════════════════════════
  // DETERMINISM
  // ═══════════════════════════════════════════════════════════
  describe('4.6 Determinism', () => {
    
    it('same_input_same_output', () => {
      const internalState = {
        open_positions: [{ position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' }]
      };
      const externalSnapshot = { positions: [] };
      
      const result1 = ReconcileEngine.reconcile(internalState, externalSnapshot);
      ReconcileEngine.reset();
      ReconcileEngine.init();
      const result2 = ReconcileEngine.reconcile(internalState, externalSnapshot);
      
      assert.strictEqual(result1.blocked, result2.blocked);
      assert.strictEqual(result1.totalFindings, result2.totalFindings);
      assert.deepStrictEqual(
        result1.findings.map(f => f.type),
        result2.findings.map(f => f.type)
      );
    });

    it('getFindingsByType_filters_correctly', () => {
      const internalState = {
        open_positions: [
          { position_id: 'pos_1', symbol: 'BTC-PERP', size: 1.0, side: 'long' },
          { position_id: 'pos_2', symbol: 'ETH-PERP', size: 2.0, side: 'long' }
        ]
      };
      const externalSnapshot = { positions: [] };
      
      const result = ReconcileEngine.reconcile(internalState, externalSnapshot);
      const ghosts = ReconcileEngine.getFindingsByType(result.findings, 'GHOST_POSITION');
      
      assert.strictEqual(ghosts.length, 2);
      assert.ok(ghosts.every(f => f.type === 'GHOST_POSITION'));
    });
  });
});
