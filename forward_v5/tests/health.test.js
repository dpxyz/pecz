/**
 * Block 3.2 Tests: Health Service
 *
 * Tests: 15+ test cases for health.js
 * Coverage: Registration, watchdogs, checks, alerting, monitoring loop
 */

const test = require('node:test');
const assert = require('node:assert');

// Clear module cache before each test
function clearHealthCache() {
  delete require.cache[require.resolve('../src/health.js')];
}

// Cleanup helper
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
// Test Suite: Health Service
// ============================================================================

test('T1: Register health check', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  let checkCalled = false;
  Health.register('test_check', async () => {
    checkCalled = true;
    return { status: 'healthy', details: {} };
  });
  
  const report = await Health.runChecks();
  assert.strictEqual(checkCalled, true, 'Check should be called');
  assert.ok(report.checks.find(c => c.name === 'test_check'), 'Check should be in report');
  
  await cleanup();
});

test('T2: Health check returns correct status', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('failing_check', async () => {
    return { status: 'unhealthy', details: { reason: 'test' }, severity: 'WARN' };
  });
  
  const report = await Health.runChecks();
  const check = report.checks.find(c => c.name === 'failing_check');
  
  assert.ok(check, 'Failing check should be in report');
  assert.strictEqual(check.status, 'unhealthy', 'Status should be unhealthy');
  assert.strictEqual(check.healthy, false, 'healthy flag should be false');
  
  await cleanup();
});

test('T3: Watchdog detects stale data', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Simulate stale data (60 seconds ago)
  const staleTime = Date.now() - 60000;
  
  Health.watchdog('tick', 30000, () => staleTime, { severity: 'CRITICAL' });
  
  const report = await Health.runChecks();
  const watchdog = report.checks.find(c => c.name === 'watchdog_tick');
  
  assert.ok(watchdog, 'Watchdog should be in report');
  assert.strictEqual(watchdog.status, 'stale', 'Should detect stale');
  assert.strictEqual(watchdog.severity, 'CRITICAL', 'Should be CRITICAL');
  assert.strictEqual(watchdog.healthy, false, 'Should not be healthy');
  
  await cleanup();
});

test('T4: Watchdog passes fresh data', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Simulate fresh data (1 second ago)
  const freshTime = Date.now() - 1000;
  
  Health.watchdog('tick', 30000, () => freshTime);
  
  const report = await Health.runChecks();
  const watchdog = report.checks.find(c => c.name === 'watchdog_tick');
  
  assert.ok(watchdog, 'Watchdog should be in report');
  assert.strictEqual(watchdog.status, 'healthy', 'Should be healthy');
  assert.strictEqual(watchdog.healthy, true, 'healthy flag should be true');
  
  await cleanup();
});

test('T5: Overall status calculation', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Register mix of checks
  Health.register('healthy_check', async () => ({ status: 'healthy' }));
  Health.register('warn_check', async () => ({ status: 'degraded', severity: 'WARN' }));
  Health.register('critical_check', async () => ({ status: 'failed', severity: 'CRITICAL' }));
  
  const report = await Health.runChecks();
  
  assert.strictEqual(report.overallStatus, 'critical', 'Should be critical with CRITICAL check');
  assert.strictEqual(report.summary.critical, 1, 'Should count 1 critical');
  assert.strictEqual(report.summary.degraded, 1, 'Should count 1 degraded');
  assert.strictEqual(report.summary.healthy, 1, 'Should count 1 healthy');
  
  await cleanup();
});

test('T6: Health check timeout', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('slow_check', async () => {
    await new Promise(r => setTimeout(r, 10000));
    return { status: 'healthy' };
  }, { timeout: 100 }); // 100ms timeout
  
  const report = await Health.runChecks();
  const check = report.checks.find(c => c.name === 'slow_check');
  
  assert.ok(check, 'Check should be in report');
  assert.strictEqual(check.status, 'error', 'Should timeout with error');
  assert.ok(check.details.error.includes('Timeout'), 'Should mention timeout');
  
  await cleanup();
});

test('T7: Monitoring start/stop', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  let checkCount = 0;
  Health.register('counter', async () => {
    checkCount++;
    return { status: 'healthy' };
  });
  
  // Start with short interval
  Health.startMonitoring({ interval: 100 });
  
  // Wait for 2 checks (initial + one interval)
  await new Promise(r => setTimeout(r, 250));
  
  assert.ok(checkCount >= 2, 'Should have run multiple checks');
  
  Health.stopMonitoring();
  const countAfterStop = checkCount;
  
  // Wait and verify no more checks
  await new Promise(r => setTimeout(r, 200));
  assert.strictEqual(checkCount, countAfterStop, 'Should stop monitoring');
  
  await cleanup();
});

test('T8: Configure alerts', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  // Should not throw
  Health.configureAlerts({
    discordWebhook: 'https://discord.com/api/webhooks/test',
    minSeverity: 'CRITICAL',
    logToFile: true
  });
  
  // Register a failing check
  Health.register('failing', async () => ({
    status: 'unhealthy',
    severity: 'WARN'
  }));
  
  // Run check - should complete without error
  const report = await Health.runChecks();
  assert.ok(report, 'Should generate report');
  
  await cleanup();
});

test('T9: Get status returns current state', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  const status = Health.getStatus();
  
  assert.ok(status.timestamp, 'Should have timestamp');
  assert.strictEqual(status.isMonitoring, false, 'Should not be monitoring initially');
  
  await cleanup();
});

test('T10: Health check throws handled gracefully', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('throwing', async () => {
    throw new Error('Check failed');
  });
  
  const report = await Health.runChecks();
  const check = report.checks.find(c => c.name === 'throwing');
  
  assert.ok(check, 'Should have check result');
  assert.strictEqual(check.status, 'error', 'Should have error status');
  assert.ok(check.details.error.includes('Check failed'), 'Should capture error');
  
  await cleanup();
});

test('T11: Multiple watchdogs work independently', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  const staleTime = Date.now() - 60000;
  const freshTime = Date.now() - 1000;
  
  Health.watchdog('stale', 10000, () => staleTime);
  Health.watchdog('fresh', 10000, () => freshTime);
  
  const report = await Health.runChecks();
  
  const stale = report.checks.find(c => c.name === 'watchdog_stale');
  const fresh = report.checks.find(c => c.name === 'watchdog_fresh');
  
  assert.ok(stale, 'Stale watchdog exists');
  assert.ok(fresh, 'Fresh watchdog exists');
  assert.strictEqual(stale.healthy, false, 'Stale should be unhealthy');
  assert.strictEqual(fresh.healthy, true, 'Fresh should be healthy');
  
  await cleanup();
});

test('T12: Report structure valid', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('check1', async () => ({ status: 'healthy' }));
  
  const report = await Health.runChecks();
  
  assert.ok(report.timestamp, 'Should have timestamp');
  assert.ok(report.overallStatus, 'Should have overallStatus');
  assert.ok(Array.isArray(report.checks), 'Should have checks array');
  assert.ok(report.summary, 'Should have summary');
  assert.strictEqual(typeof report.summary.total, 'number', 'Summary should have total');
  assert.strictEqual(typeof report.summary.healthy, 'number', 'Summary should have healthy count');
  
  await cleanup();
});

test('T13: Watchdog onStale callback', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  let staleCalled = false;
  const staleTime = Date.now() - 60000;
  
  Health.watchdog('test', 10000, () => staleTime, {
    severity: 'WARN',
    onStale: (result) => {
      staleCalled = true;
    }
  });
  
  await Health.runChecks();
  
  assert.strictEqual(staleCalled, true, 'onStale should be called');
  
  await cleanup();
});

test('T14: Severity levels respected', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('warn_check', async () => ({
    status: 'degraded',
    severity: 'WARN'
  }), { severity: 'WARN' });
  
  Health.register('critical_check', async () => ({
    status: 'failed',
    severity: 'CRITICAL'
  }), { severity: 'CRITICAL' });
  
  const report = await Health.runChecks();
  
  const warn = report.checks.find(c => c.name === 'warn_check');
  const critical = report.checks.find(c => c.name === 'critical_check');
  
  assert.strictEqual(warn.severity, 'WARN', 'Should have WARN severity');
  assert.strictEqual(critical.severity, 'CRITICAL', 'Should have CRITICAL severity');
  
  await cleanup();
});

test('T15: Duplicate monitoring start is safe', async (t) => {
  await cleanup();
  clearHealthCache();
  
  const Health = require('../src/health.js');
  
  Health.register('check', async () => ({ status: 'healthy' }));
  
  // Start twice
  Health.startMonitoring({ interval: 1000 });
  Health.startMonitoring({ interval: 1000 });
  
  // Should only have one interval
  const status = Health.getStatus();
  assert.strictEqual(status.isMonitoring, true, 'Should be monitoring');
  
  Health.stopMonitoring();
  
  await cleanup();
});

// Cleanup after all tests
test.after(async () => {
  await cleanup();
});
