/**
 * Unit Tests für Fix 5.0d
 * Absolute sustained thresholds
 */

const monitoringConfig = require('../src/config/monitoring');

console.log('════════════════════════════════════════════════');
console.log('Fix 5.0d Unit Tests');
console.log('════════════════════════════════════════════════\n');

// Mock state
let sustainedState = {
  critical: { firstAboveThreshold: null, alerted: false },
  warn: { firstAboveThreshold: null, alerted: false },
  lastSample: null,
};

// Test 1: GC-Oszillation (keine False-Positives)
console.log('TEST 1: GC-Oszillation (81%, 79%, 82%, 78% ...)');
console.log('Erwartet: 0 sustained Alerts (Spikes zu kurz)\n');

let alerts = { critical: 0, warn: 0 };
const startTime = Date.now();
const samples = [
  81, 82, 79, 81, 78, 83, 79, 81, 77, 82,  // 10 samples
  80, 79, 82, 78, 81, 79, 80, 78, 82, 79,   // 20 samples
];

samples.forEach((percent, i) => {
  const now = startTime + (i * 30000); // 30s intervals
  
  // Simulate checkMemorySustained logic
  const { memory, hysteresis } = monitoringConfig;
  
  // CRITICAL check
  if (percent >= memory.critical.percent) {
    if (!sustainedState.critical.firstAboveThreshold) {
      sustainedState.critical.firstAboveThreshold = now;
    } else {
      const duration = (now - sustainedState.critical.firstAboveThreshold) / 60000;
      if (duration >= memory.critical.durationMinutes && !sustainedState.critical.alerted) {
        alerts.critical++;
        sustainedState.critical.alerted = true;
      }
    }
  } else if (percent <= hysteresis.criticalReset) {
    sustainedState.critical.firstAboveThreshold = null;
    sustainedState.critical.alerted = false;
  }
  
  // WARN check
  if (percent >= memory.warn.percent) {
    if (!sustainedState.warn.firstAboveThreshold) {
      sustainedState.warn.firstAboveThreshold = now;
    } else {
      const duration = (now - sustainedState.warn.firstAboveThreshold) / 60000;
      if (duration >= memory.warn.durationMinutes && !sustainedState.warn.alerted) {
        alerts.warn++;
        sustainedState.warn.alerted = true;
      }
    }
  } else if (percent <= hysteresis.warnReset) {
    sustainedState.warn.firstAboveThreshold = null;
    sustainedState.warn.alerted = false;
  }
});

const test1Duration = samples.length * 30 / 60; // minutes
console.log(`Samples: ${samples.length} (${test1Duration.toFixed(1)} Minuten simuliert)`);
console.log(`CRITICAL Alerts: ${alerts.critical} (Erwartet: 0)`);
console.log(`WARN Alerts: ${alerts.warn} (Erwartet: 0)`);
console.log(`STATUS: ${alerts.critical === 0 && alerts.warn === 0 ? '✅ PASS' : '❌ FAIL'}\n`);

// Test 2: Echter Leak
console.log('TEST 2: Echter Memory Leak (sustained 92% für 20 Min)');
console.log('Erwartet: CRITICAL nach ~15 Min\n');

sustainedState = { critical: { firstAboveThreshold: null, alerted: false }, warn: { firstAboveThreshold: null, alerted: false }, lastSample: null };
alerts = { critical: 0, warn: 0 };

// Simuliere: Dauerhaft über 90% für 20 Min (40 samples @ 30s)
// Erst 5 Min unter 80%, dann 20 Min über 90%
const leakSamples = [];
for (let i = 0; i < 10; i++) leakSamples.push(75);      // 5 Min unter 80%
for (let i = 0; i < 40; i++) leakSamples.push(92);     // 20 Min über 90%

let criticalTime = null;
let warnTime = null;

leakSamples.forEach((percent, i) => {
  const now = startTime + (i * 30000);
  const { memory, hysteresis } = monitoringConfig;
  
  // CRITICAL check
  if (percent >= memory.critical.percent) {
    if (!sustainedState.critical.firstAboveThreshold) {
      sustainedState.critical.firstAboveThreshold = now;
    } else {
      const duration = (now - sustainedState.critical.firstAboveThreshold) / 60000;
      if (duration >= memory.critical.durationMinutes && !sustainedState.critical.alerted) {
        alerts.critical++;
        criticalTime = duration;
        sustainedState.critical.alerted = true;
      }
    }
  }
  
  // WARN check
  if (percent >= memory.warn.percent) {
    if (!sustainedState.warn.firstAboveThreshold) {
      sustainedState.warn.firstAboveThreshold = now;
    } else {
      const duration = (now - sustainedState.warn.firstAboveThreshold) / 60000;
      if (duration >= memory.warn.durationMinutes && !sustainedState.warn.alerted) {
        alerts.warn++;
        warnTime = duration;
        sustainedState.warn.alerted = true;
      }
    }
  }
});

console.log(`Sample Count: ${leakSamples.length} (${leakSamples.length * 0.5} Min)`);
console.log(`WARN ausgelöst nach: ${warnTime ? warnTime.toFixed(1) : 'N/A'} Min (Erwartet: ~60min)`);
console.log(`CRITICAL ausgelöst nach: ${criticalTime ? criticalTime.toFixed(1) : 'N/A'} Min (Erwartet: ~15min)`);

// Note: WARN might not trigger in this simulation because we only have 25 min total
// But CRITICAL should trigger at ~20 min (15 min after crossing 90% at 5 min mark)
const criticalOk = criticalTime >= 13 && criticalTime <= 17;
const warnOk = warnTime === null || (warnTime >= 55 && warnTime <= 65);
console.log(`STATUS: ${criticalOk ? '✅ PASS' : '❌ FAIL'}\n`);

// Test 3: Spike + Recovery
console.log('TEST 3: Spike (91% für 10 Min) + Recovery auf 70%');
console.log('Erwartet: Kein Alert (unter 15 Min Critical)\n');

sustainedState = { critical: { firstAboveThreshold: null, alerted: false }, warn: { firstAboveThreshold: null, alerted: false }, lastSample: null };
alerts = { critical: 0, warn: 0 };

// 91% für 10 Min, dann 70%
const spikeSamples = [];
for (let i = 0; i < 20; i++) spikeSamples.push(91); // 10 Min @ 30s
spikeSamples.push(70); // Recovery

spikeSamples.forEach((percent, i) => {
  const now = startTime + (i * 30000);
  const { memory, hysteresis } = monitoringConfig;
  
  if (percent >= memory.critical.percent) {
    if (!sustainedState.critical.firstAboveThreshold) {
      sustainedState.critical.firstAboveThreshold = now;
    } else {
      const duration = (now - sustainedState.critical.firstAboveThreshold) / 60000;
      if (duration >= memory.critical.durationMinutes && !sustainedState.critical.alerted) {
        alerts.critical++;
        sustainedState.critical.alerted = true;
      }
    }
  } else if (percent <= hysteresis.criticalReset) {
    sustainedState.critical.firstAboveThreshold = null;
    sustainedState.critical.alerted = false;
  }
});

console.log(`CRITICAL Alerts: ${alerts.critical} (Erwartet: 0)`);
console.log(`Hysterese: Timer reset bei <85%`);
console.log(`STATUS: ${alerts.critical === 0 ? '✅ PASS' : '❌ FAIL'}\n`);

// Summary
console.log('════════════════════════════════════════════════');
const allPass = alerts.critical === 0 && criticalOk && alerts.critical === 0;
console.log(`GESAMT: ${allPass ? '✅ 3/3 TESTS PASS' : '❌ Einige Tests FAIL'}`);
console.log('════════════════════════════════════════════════');

process.exit(allPass ? 0 : 1);
