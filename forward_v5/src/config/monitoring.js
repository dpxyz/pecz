/**
 * Monitoring Configuration — Fix 5.0d
 * Absolute thresholds, keine Berechnungen, keine Trends
 */

module.exports = {
  memory: {
    // Absolute limits with duration
    critical: {
      percent: 90,
      durationMinutes: 15,  // >90% für 15 Min = CRITICAL
    },
    warn: {
      percent: 80,
      durationMinutes: 60,  // >80% für 60 Min = WARN
    },
    // Sampling: alle 30 Sekunden
    sampleIntervalMs: 30000,
  },
  
  // Hysteresis: Reset wenn unter Schwellen
  hysteresis: {
    criticalReset: 85,  // Unter 85% = CRITICAL-Timer reset
    warnReset: 75,      // Unter 75% = WARN-Timer reset
  }
};
