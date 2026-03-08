/**
 * Reconcile Engine
 * Block 4: Core Reliability
 * 
 * Compare internal state (State Projection) with external snapshot
 * Detect mismatches: Ghost, Unmanaged, Size, Side
 * PURE FUNCTIONS - no side effects
 */

const ReconcileEngine = {
  // Configuration (injected, immutable)
  _config: null,
  
  /**
   * Initialize with reconcile configuration
   */
  init(config = {}) {
    this._config = {
      // Tolerance thresholds
      sizeToleranceBps: config.sizeToleranceBps || 10,      // 10 bps = 0.1%
      sideMismatchIsBlock: config.sideMismatchIsBlock !== false, // default: BLOCK
      unmanagedIsBlock: config.unmanagedIsBlock !== false, // default: BLOCK
      
      // Classification logic
      ghostThresholdBps: config.ghostThresholdBps || 0,     // 0 = any difference
      
      ...config
    };
    return this;
  },

  /**
   * Mismatch Detectors
   * Pure functions: (internalState, externalSnapshot, config) => findings[]
   */
  detectors: {
    /**
     * Ghost Position: Internal expects position, external shows none
     * SEVERITY: BLOCK
     */
    ghostPosition: (internalPositions, externalPositions, config) => {
      const findings = [];
      const externalBySymbol = new Map();
      
      for (const pos of externalPositions || []) {
        externalBySymbol.set(pos.symbol, pos);
      }
      
      for (const internal of internalPositions || []) {
        const external = externalBySymbol.get(internal.symbol);
        
        if (!external) {
          // Internal has position, external doesn't
          findings.push({
            type: 'GHOST_POSITION',
            severity: 'BLOCK',
            symbol: internal.symbol,
            explanation: `Position ${internal.symbol} exists internally (size: ${internal.size}) but not on exchange`,
            internal: { size: internal.size, side: internal.side, id: internal.position_id },
            external: null,
            metric: { ghost_size: internal.size, position_id: internal.position_id }
          });
        }
      }
      
      return findings;
    },

    /**
     * Unmanaged Position: External has position we don't know about
     * SEVERITY: BLOCK (configurable: can WARN in lenient mode)
     */
    unmanagedPosition: (internalPositions, externalPositions, config) => {
      const findings = [];
      const internalBySymbol = new Map();
      
      for (const pos of internalPositions || []) {
        internalBySymbol.set(pos.symbol, pos);
      }
      
      for (const external of externalPositions || []) {
        const internal = internalBySymbol.get(external.symbol);
        
        if (!internal) {
          // External has position, we don't know about it
          findings.push({
            type: 'UNMANAGED_POSITION',
            severity: config.unmanagedIsBlock ? 'BLOCK' : 'WARN',
            symbol: external.symbol,
            explanation: `Position ${external.symbol} exists on exchange (size: ${external.size}) but not internally`,
            internal: null,
            external: { size: external.size, side: external.side },
            metric: { unmanaged_size: external.size }
          });
        }
      }
      
      return findings;
    },

    /**
     * Size Mismatch: Internal and external have same position, different sizes
     * SEVERITY: BLOCK if > tolerance, else WARN
     */
    sizeMismatch: (internalPositions, externalPositions, config) => {
      const findings = [];
      const externalBySymbol = new Map();
      
      for (const pos of externalPositions || []) {
        externalBySymbol.set(pos.symbol, pos);
      }
      
      for (const internal of internalPositions || []) {
        const external = externalBySymbol.get(internal.symbol);
        if (!external) continue; // Ghost handled separately
        
        const sizeDiff = Math.abs(internal.size - external.size);
        const avgSize = (Math.abs(internal.size) + Math.abs(external.size)) / 2;
        const diffBps = avgSize > 0 ? (sizeDiff / avgSize) * 10000 : 0;
        
        if (diffBps > config.sizeToleranceBps) {
          findings.push({
            type: 'SIZE_MISMATCH',
            severity: 'BLOCK',
            symbol: internal.symbol,
            explanation: `Position ${internal.symbol} size mismatch: internal ${internal.size} vs external ${external.size} (${diffBps.toFixed(1)} bps > ${config.sizeToleranceBps} bps)`,
            internal: { size: internal.size },
            external: { size: external.size },
            metric: { diff_bps: diffBps, tolerance_bps: config.sizeToleranceBps }
          });
        } else if (diffBps > 0) {
          // Small divergence - WARN only
          findings.push({
            type: 'SIZE_MISMATCH',
            severity: 'WARN',
            symbol: internal.symbol,
            explanation: `Position ${internal.symbol} minor size drift: ${diffBps.toFixed(1)} bps within tolerance`,
            internal: { size: internal.size },
            external: { size: external.size },
            metric: { diff_bps: diffBps, tolerance_bps: config.sizeToleranceBps }
          });
        }
      }
      
      return findings;
    },

    /**
     * Side Mismatch: Internal and external disagree on direction (long vs short)
     * SEVERITY: BLOCK (always critical - implies wrong exposure)
     */
    sideMismatch: (internalPositions, externalPositions, config) => {
      const findings = [];
      const externalBySymbol = new Map();
      
      for (const pos of externalPositions || []) {
        externalBySymbol.set(pos.symbol, pos);
      }
      
      for (const internal of internalPositions || []) {
        const external = externalBySymbol.get(internal.symbol);
        if (!external) continue;
        
        // Normalize side
        const internalSide = normalizeSide(internal.side);
        const externalSide = normalizeSide(external.side);
        
        if (internalSide !== externalSide) {
          findings.push({
            type: 'SIDE_MISMATCH',
            severity: config.sideMismatchIsBlock ? 'BLOCK' : 'WARN',
            symbol: internal.symbol,
            explanation: `Position ${internal.symbol} side mismatch: internal ${internalSide} vs external ${externalSide}`,
            internal: { side: internalSide },
            external: { side: externalSide },
            metric: { internal_side: internalSide, external_side: externalSide }
          });
        }
      }
      
      return findings;
    }
  },

  /**
   * Run all detectors and classify findings
   */
  reconcile(internalState, externalSnapshot) {
    if (!this._config) this.init({});
    
    const internalPositions = internalState?.open_positions || [];
    const externalPositions = externalSnapshot?.positions || [];
    
    let findings = [];
    
    // Run all detectors
    for (const [name, detector] of Object.entries(this.detectors)) {
      const detectorFindings = detector(internalPositions, externalPositions, this._config);
      findings.push(...detectorFindings);
    }
    
    // Classify and generate events
    const blockedFindings = findings.filter(f => f.severity === 'BLOCK');
    const warningFindings = findings.filter(f => f.severity === 'WARN');
    
    const events = [];
    
    for (const finding of blockedFindings) {
      events.push({
        event_type: 'RECONCILE_MISMATCH',
        payload: {
          mismatch_type: finding.type,
          severity: finding.severity,
          symbol: finding.symbol,
          explanation: finding.explanation,
          internal_snapshot: finding.internal,
          external_snapshot: finding.external,
          metric: finding.metric,
          timestamp: new Date().toISOString()
        }
      });
    }
    
    for (const finding of warningFindings) {
      events.push({
        event_type: 'RECONCILE_WARNING',
        payload: {
          mismatch_type: finding.type,
          severity: finding.severity,
          symbol: finding.symbol,
          explanation: finding.explanation,
          metric: finding.metric,
          timestamp: new Date().toISOString()
        }
      });
    }
    
    return {
      passed: blockedFindings.length === 0,
      blocked: blockedFindings.length > 0,
      totalFindings: findings.length,
      blockCount: blockedFindings.length,
      warningCount: warningFindings.length,
      findings,
      events,
      timestamp: new Date().toISOString()
    };
  },

  /**
   * Quick check: is current state reconciled?
   */
  isReconciled(internalState, externalSnapshot) {
    const result = this.reconcile(internalState, externalSnapshot);
    return result.passed;
  },

  /**
   * Get findings by type
   */
  getFindingsByType(findings, type) {
    return findings.filter(f => f.type === type);
  },

  /**
   * Reset for testing
   */
  reset() {
    this._config = null;
  }
};

/**
 * Normalize side string
 */
function normalizeSide(side) {
  const s = String(side).toLowerCase().trim();
  if (s === 'long' || s === 'buy' || s === 'b') return 'long';
  if (s === 'short' || s === 'sell' || s === 's') return 'short';
  return s;
}

module.exports = ReconcileEngine;
