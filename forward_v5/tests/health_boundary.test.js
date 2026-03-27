/**
 * Block 3.2 Boundary Tests: SAFETY vs OBSERVABILITY
 *
 * Tests: Boundary separation between trading-critical and non-critical checks
 */

const test = require('node:test');
const assert = require('node:assert');

function clearHealthCache() {
  delete require.cache[require.resolve('../src/health.js')];
}

async function cleanup() {
  try {
    const Health = require('../src/health.js');
    Health.stopMonitoring();
    Health._reset();
  } catch (e) {
    // Ignore
  }
}

// ============================================================================
// Boundary Tests
// ============================================================================

test('T1: DOMAIN constant exists', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  assert.ok(Health.DOMAIN, 'Has DOMAIN constant');
  assert.ok(Health.DOMAIN.SAFETY, 'Has SAFETY domain');
  assert.ok(Health.DOMAIN.OBSERVABILITY, 'Has OBSERVABILITY domain');
  
  await cleanup();
});

test('T2: SAFETY check triggers pause on failure', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Register a SAFETY check that will fail
  Health.register('test_safety', async () => ({
    status: 'failed',
    details: { reason: 'test' }
  }), { 
    domain: Health.DOMAIN.SAFETY,
    severity: 'CRITICAL' 
  });
  
  const report = await Health.runChecks();
  
  // SAFETY failure should trigger pause
  assert.ok(Health.isPaused(), 'SAFETY failure should trigger isPaused');
  assert.strictEqual(report.isPaused, true, 'Report should show isPaused');
  
  await cleanup();
});

test('T3: OBSERVABILITY check does NOT trigger pause', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Register OBSERVABILITY check that fails
  Health.register('test_obs', async () => ({
    status: 'failed',
    details: { reason: 'test' }
  }), { 
    domain: Health.DOMAIN.OBSERVABILITY,
    severity: 'WARN' 
  });
  
  const report = await Health.runChecks();
  
  // OBSERVABILITY failure should NOT pause
  assert.strictEqual(Health.isPaused(), false, 'OBSERVABILITY should not trigger pause');
  
  await cleanup();
});

test('T4: Safety checks are defined', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Verify built-in safety checks exist
  assert.ok(Health.safetyChecks.event_store, 'event_store check defined');
  assert.ok(Health.safetyChecks.state_projection, 'state_projection check defined');
  assert.ok(Health.safetyChecks.risk_engine, 'risk_engine check defined');
  assert.ok(Health.safetyChecks.watchdog_tick, 'watchdog_tick check defined');
  assert.ok(Health.safetyChecks.reconcile_positions, 'reconcile_positions check defined');
  
  // Verify they are all SAFETY domain
  for (const [name, config] of Object.entries(Health.safetyChecks)) {
    assert.strictEqual(config.domain, Health.DOMAIN.SAFETY, `${name} should be SAFETY`);
  }
  
  await cleanup();
});

test('T5: Observability checks are defined', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Verify built-in observability checks
  assert.ok(Health.observabilityChecks.discord_webhook, 'discord_webhook check defined');
  assert.ok(Health.observabilityChecks.logger_fallback, 'logger_fallback check defined');
  assert.ok(Health.observabilityChecks.check_latency, 'check_latency check defined');
  
  // Verify they are all OBSERVABILITY domain
  for (const [name, config] of Object.entries(Health.observabilityChecks)) {
    assert.strictEqual(config.domain, Health.DOMAIN.OBSERVABILITY, `${name} should be OBSERVABILITY`);
  }
  
  await cleanup();
});

test('T6: Resume trading works', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Make it paused
  Health.register('safety_fail', async () => ({ status: 'failed' }), {
    domain: Health.DOMAIN.SAFETY
  });
  
  await Health.runChecks();
  assert.strictEqual(Health.isPaused(), true, 'Should be paused');
  
  // Resume
  const resumed = Health.resumeTrading();
  assert.strictEqual(resumed, true, 'resumeTrading should return true');
  assert.strictEqual(Health.isPaused(), false, 'Should not be paused after resume');
  
  await cleanup();
});

test('T7: Report shows domain summary', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('safety_check', async () => ({ status: 'failed' }), {
    domain: Health.DOMAIN.SAFETY
  });
  
  Health.register('obs_check', async () => ({ status: 'failed' }), {
    domain: Health.DOMAIN.OBSERVABILITY
  });
  
  const report = await Health.runChecks();
  
  assert.ok(report.summary.byDomain, 'Report has byDomain summary');
  assert.strictEqual(report.summary.byDomain.SAFETY.failed, 1, 'Shows SAFETY failures');
  assert.strictEqual(report.summary.byDomain.OBSERVABILITY.failed, 1, 'Shows OBSERVABILITY failures');
  
  await cleanup();
});

test('T8: Watchdog defaults to SAFETY domain', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Register watchdog without domain (should default to SAFETY)
  Health.watchdog('test1', 1000, () => Date.now());
  
  const report = await Health.runChecks();
  const wd = report.checks.find(c => c.name === 'watchdog_test1');
  
  assert.ok(wd, 'Watchdog in report');
  assert.strictEqual(wd.domain, Health.DOMAIN.SAFETY, 'Watchdog defaults to SAFETY');
  
  await cleanup();
});

test('T9: Mixed health report classification', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Healthy SAFETY, failing OBSERVABILITY => degraded (not paused)
  Health.register('safe_healthy', async () => ({ status: 'healthy' }), {
    domain: Health.DOMAIN.SAFETY
  });
  
  Health.register('obs_failing', async () => ({ status: 'slow' }), {
    domain: Health.DOMAIN.OBSERVABILITY,
    severity: 'WARN'
  });
  
  const report = await Health.runChecks();
  
  assert.strictEqual(report.overallStatus, 'degraded', 'OBS-only = degraded');
  assert.strictEqual(Health.isPaused(), false, 'Not paused');
  
  await cleanup();
});

test('T10: SAFETY watchdog stale triggers pause', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Stale timestamp (60 seconds ago)
  const staleTime = Date.now() - 60000;
  
  Health.watchdog('stale_tick', 10000, () => staleTime, {
    domain: Health.DOMAIN.SAFETY,
    severity: 'CRITICAL'
  });
  
  await Health.runChecks();
  
  // SAFETY stale should trigger pause
  assert.strictEqual(Health.isPaused(), true, 'SAFETY stale watchdog should pause');
  
  await cleanup();
});

test('T11: OBSERVABILITY watchdog stale does NOT pause', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  const staleTime = Date.now() - 60000;
  
  Health.watchdog('stale_latency', 10000, () => staleTime, {
    domain: Health.DOMAIN.OBSERVABILITY,
    severity: 'WARN'
  });
  
  await Health.runChecks();
  
  assert.strictEqual(Health.isPaused(), false, 'OBSERVABILITY stale should NOT pause');
  
  await cleanup();
});

test('T12: Register defaults to OBSERVABILITY', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('no_domain', async () => ({ status: 'healthy' }));
  
  const report = await Health.runChecks();
  const check = report.checks.find(c => c.name === 'no_domain');
  
  assert.strictEqual(check.domain, Health.DOMAIN.OBSERVABILITY, 'Default is OBSERVABILITY');
  
  await cleanup();
});

test('T13: Health events are emitted', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Can't easily test EventStore emission without mocking
  // Just verify no throw
  Health.register('test_event', async () => ({ status: 'healthy' }), {
    domain: Health.DOMAIN.SAFETY
  });
  
  let threw = false;
  try {
    await Health.runChecks();
  } catch (e) {
    threw = true;
  }
  
  assert.strictEqual(threw, false, 'Should emit events without error');
  
  await cleanup();
});

test('T14: Status includes isPaused flag', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Make paused
  Health.register('pause_trigger', async () => ({ status: 'failed' }), {
    domain: Health.DOMAIN.SAFETY
  });
  await Health.runChecks();
  
  const status = Health.getStatus();
  
  assert.strictEqual(status.isPaused, true, 'Status shows isPaused');
  assert.strictEqual(status.isMonitoring, false, 'Shows monitoring status');
  
  await cleanup();
});

test('T15: Safety checks show in report with correct domain', async () => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('safety_critical', async () => ({ status: 'failed' }), {
    domain: Health.DOMAIN.SAFETY,
    severity: 'CRITICAL'
  });
  
  Health.register('obs_warning', async () => ({ status: 'slow' }), {
    domain: Health.DOMAIN.OBSERVABILITY,
    severity: 'WARN'
  });
  
  const report = await Health.runChecks();
  
  const safety = report.checks.find(c => c.name === 'safety_critical');
  const obs = report.checks.find(c => c.name === 'obs_warning');
  
  assert.strictEqual(safety.domain, Health.DOMAIN.SAFETY, 'SAFETY check has correct domain');
  assert.strictEqual(obs.domain, Health.DOMAIN.OBSERVABILITY, 'OBSERVABILITY check has correct domain');
  
  await cleanup();
});

// Cleanup
test.after(async () => {
  await cleanup();
});
