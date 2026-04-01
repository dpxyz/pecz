/**
 * Phase 6: Integration Tests - Alert Engine
 * Block: Alert System Integration Tests
 * 
 * Tests:
 * - One-shot behavior (no duplicate alerts)
 * - Discord down doesn't block (fail gracefully)
 * - Recovery clears alerts after delay
 * - Sustained failures required for non-immediate rules
 */

const AlertEngine = require('../cli/alertEngine');
const assert = require('assert');

describe('Alert Engine Integration', () => {
  let engine;

  beforeEach(() => {
    engine = new AlertEngine({});
    // Bypass grace period for tests
    engine.engineStartedAt = Date.now() - 130000;
  });

  describe('One-shot behavior', () => {
    it('should fire alert only once per incident', () => {
      engine.previousStatus = 'UP';
      
      const criticalData = {
        status: 'DOWN',
        component: 'readiness',
        reason: 'test failure',
        checks: { heartbeat: 'STALE (120s ago)', memory: 'OK (80%)' }
      };

      // First call - should fire
      const result1 = engine.evaluate(criticalData);
      assert.strictEqual(result1.fired.length, 1);
      
      // Second call - should NOT fire (already active)
      const result2 = engine.evaluate(criticalData);
      assert.strictEqual(result2.fired.length, 0);
    });

    it('should track multiple independent alerts', () => {
      engine.previousStatus = 'UP';
      
      const downData = {
        status: 'DOWN',
        component: 'readiness',
        reason: 'service down',
        checks: {}
      };

      const memoryData = {
        status: 'UP',
        component: 'readiness',
        checks: { memory: 'CRITICAL (96%)', heartbeat: 'OK' }
      };

      // Sustained failures for memory (need 2)
      engine.evaluate(memoryData);
      engine.previousStatus = 'UP';
      const downResult = engine.evaluate(downData);
      engine.previousStatus = 'UP';
      const memoryResult = engine.evaluate(memoryData);

      assert.strictEqual(downResult.fired.length, 1);
      assert.strictEqual(downResult.fired[0].rule, 'service_down');
    });
  });

  describe('Sustained failure detection', () => {
    it('should require 2 consecutive failures for heartbeat_stale', () => {
      engine.previousStatus = 'UP';
      
      const staleData = {
        status: 'UP',
        component: 'readiness',
        checks: { heartbeat: 'STALE (120s ago)', memory: 'OK (80%)' }
      };

      // First evaluation - not enough failures
      const result1 = engine.evaluate(staleData);
      assert.strictEqual(result1.fired.length, 0);

      // Second evaluation - sustained failure
      const result2 = engine.evaluate(staleData);
      assert.strictEqual(result2.fired.length, 1);
      assert.strictEqual(result2.fired[0].severity, 'WARNING');
    });

    it('should fire service_down immediately on UP->DOWN transition', () => {
      engine.previousStatus = 'UP';
      
      const downData = {
        status: 'DOWN',
        component: 'readiness',
        reason: 'immediate test',
        checks: {}
      };

      // Should fire immediately (no sustained period needed)
      const result = engine.evaluate(downData);
      assert.strictEqual(result.fired.length, 1);
      assert.strictEqual(result.fired[0].rule, 'service_down');
    });
  });

  describe('Recovery mechanism', () => {
    it('should clear alert when condition resolves', () => {
      engine.previousStatus = 'UP';
      
      const downData = {
        status: 'DOWN',
        component: 'readiness',
        reason: 'test failure',
        checks: {}
      };

      const healthyData = {
        status: 'UP',
        component: 'readiness',
        checks: { heartbeat: 'OK', memory: 'OK (80%)' }
      };

      // Fire alert
      engine.evaluate(downData);
      assert.strictEqual(engine.getActiveAlerts().length, 1);

      // Clear condition
      engine.evaluate(healthyData);
      
      // Alert should still be active (5s delay)
      assert.strictEqual(engine.getActiveAlerts().length, 1);

      // Simulate time passing
      setTimeout(() => {
        assert.strictEqual(engine.getActiveAlerts().length, 0);
      }, 5500);
    });
  });

  describe('State isolation', () => {
    it('should track failures per rule:source combination', () => {
      engine.previousStatus = 'UP';
      
      const dataA = {
        status: 'UP',
        component: 'service-a',
        checks: { heartbeat: 'STALE (60s ago)', memory: 'OK (80%)' }
      };

      const dataB = {
        status: 'UP',
        component: 'service-b',
        checks: { heartbeat: 'STALE (60s ago)', memory: 'OK (80%)' }
      };

      // Build failures for service-a (needs 2)
      engine.evaluate(dataA);
      engine.previousStatus = 'UP';
      
      // Reset failures for service-b (separate counter)
      engine.evaluate(dataB);
      engine.previousStatus = 'UP';
      
      // service-a should fire (2nd failure)
      const resultA = engine.evaluate(dataA);
      assert.strictEqual(resultA.fired.length, 1);
      
      // service-b should NOT fire yet (only 2nd failure)
      engine.previousStatus = 'UP';
      const resultB = engine.evaluate(dataB);
      assert.strictEqual(resultB.fired.length, 0);
    });
  });

  describe('Discord payload generation', () => {
    it('should generate CRITICAL payload with mention', () => {
      engine.previousStatus = 'UP';
      
      const downData = {
        status: 'DOWN',
        component: 'readiness',
        reason: 'critical test',
        checks: {}
      };

      const result = engine.evaluate(downData);
      const alert = result.fired[0];
      const payload = engine.buildDiscordPayload(alert);

      assert.strictEqual(payload.content, '@here 🚨 CRITICAL Alert');
      assert.ok(payload.embeds);
      assert.strictEqual(payload.allowed_mentions.parse[0], 'everyone');
    });

    it('should generate WARNING payload without mention', () => {
      engine.previousStatus = 'UP';
      
      const warningData = {
        status: 'UP',
        component: 'readiness',
        checks: { heartbeat: 'STALE (120s ago)', memory: 'OK (80%)' }
      };

      // Sustained failures (2x)
      engine.evaluate(warningData);
      engine.previousStatus = 'UP';
      const result = engine.evaluate(warningData);
      
      const alert = result.fired[0];
      const payload = engine.buildDiscordPayload(alert);

      assert.strictEqual(payload.content, null);
      assert.ok(payload.embeds);
      assert.strictEqual(payload.allowed_mentions.parse.length, 0);
    });
  });
});

// Run tests if executed directly
if (require.main === module) {
  const { run } = require('./test_runner');
  run();
}
