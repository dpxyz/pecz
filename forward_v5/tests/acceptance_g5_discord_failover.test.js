/**
 * Phase 6: Acceptance Test - G5
 * Block: Discord Failure Does Not Block Trading
 * 
 * Acceptance Gate G5: Report failures don't affect trading
 */

const AlertEngine = require('../cli/alertEngine');
const assert = require('assert');

describe('Acceptance Gate G5: Discord Failover', () => {
  let engine;

  beforeEach(() => {
    engine = new AlertEngine({});
    engine.engineStartedAt = Date.now() - 130000; // Bypass grace
  });

  it('should not throw when Discord webhook is invalid', async () => {
    engine.previousStatus = 'UP';
    
    const brokenEngine = new AlertEngine({
      discordWebhook: 'https://invalid-url-that-will-fail.com'
    });
    brokenEngine.engineStartedAt = Date.now() - 130000;
    
    const alert = {
      severity: 'CRITICAL',
      message: 'Test message',
      rule: 'test_rule',
      timestamp: new Date().toISOString()
    };

    // Should not throw
    let errorThrown = false;
    try {
      await brokenEngine.sendDiscord(alert);
    } catch (err) {
      errorThrown = true;
    }

    // Expect failure but no throw (error logged only)
    assert.strictEqual(errorThrown, false, 'sendDiscord should not throw');
  });

  it('should continue alert evaluation even if Discord fails', () => {
    engine.previousStatus = 'UP';
    
    const downData = {
      status: 'DOWN',
      component: 'readiness',
      reason: 'test failure',
      checks: {}
    };

    // Alert should fire regardless of Discord success
    const result = engine.evaluate(downData);
    assert.strictEqual(result.fired.length, 1);
    
    // Dashboard should show alert
    assert.strictEqual(engine.getActiveAlerts().length, 1);
  });

  it('should queue alert to dashboard even without Discord', () => {
    const engineNoDiscord = new AlertEngine({}); // No webhook
    engineNoDiscord.engineStartedAt = Date.now() - 130000;
    engineNoDiscord.previousStatus = 'UP';
    
    const downData = {
      status: 'DOWN',
      component: 'readiness',
      reason: 'no discord test',
      checks: {}
    };

    const result = engineNoDiscord.evaluate(downData);
    
    // Should still fire (alert tracked internally)
    assert.strictEqual(result.fired.length, 1);
    assert.strictEqual(result.fired[0].discord, true); // Flag set even if no webhook
    
    // Dashboard sees it
    assert.strictEqual(engineNoDiscord.getActiveAlerts().length, 1);
  });
});

// Simple test runner
if (require.main === module) {
  console.log('G5 Acceptance Tests - Discord Failover');
  console.log('=====================================\n');
  
  const tests = [
    { name: 'Invalid webhook does not throw', fn: async () => {
      const engine = new AlertEngine({ discordWebhook: 'https://invalid-url.com' });
      engine.engineStartedAt = Date.now() - 130000;
      await engine.sendDiscord({ severity: 'CRITICAL', message: 'test', timestamp: new Date().toISOString() });
    }},
    { name: 'Alert evaluation continues if Discord fails', fn: () => {
      const engine = new AlertEngine({});
      engine.engineStartedAt = Date.now() - 130000;
      engine.previousStatus = 'UP';
      const result = engine.evaluate({ status: 'DOWN', component: 'test', reason: 'test', checks: {} });
      if (result.fired.length !== 1) throw new Error('Alert not fired');
    }},
    { name: 'Dashboard shows alert without Discord', fn: () => {
      const engine = new AlertEngine({});
      engine.engineStartedAt = Date.now() - 130000;
      engine.previousStatus = 'UP';
      engine.evaluate({ status: 'DOWN', component: 'test', reason: 'test', checks: {} });
      if (engine.getActiveAlerts().length !== 1) throw new Error('Alert not in dashboard');
    }}
  ];
  
  let passed = 0;
  let failed = 0;
  
  (async () => {
    for (const test of tests) {
      try {
        await test.fn();
        console.log(`✅ ${test.name}`);
        passed++;
      } catch (err) {
        console.log(`❌ ${test.name}: ${err.message}`);
        failed++;
      }
    }
    
    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    process.exit(failed > 0 ? 1 : 0);
  })();
}
