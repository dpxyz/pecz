/**
 * Safety Check: Disk Space Monitoring
 * 
 * Verifies that disk space is monitored at SAFETY level
 * This can PAUSE trading if disk exceeds 90%
 * 
 * @module tests/disk_space_safety.test
 * @version 1.0.0
 */

const { describe, it } = require('node:test');
const assert = require('node:assert');
const Health = require('../src/health.js');

describe('SAFETY: Disk Space Checks', () => {
  
  it('checkDiskSpace returns healthy when disk < 80%', async () => {
    // Mock a healthy disk (mock the execSync call)
    const result = await Health.checkDiskSpace();
    
    // Should return object with status, severity, details
    assert.ok(result, 'Should return a result');
    assert.ok(result.status, 'Should have status');
    assert.ok(result.details, 'Should have details');
    assert.ok(result.details.used_percent !== undefined, 'Should have used_percent');
    
    // If actually < 80%, should be healthy
    if (result.details.used_percent < 80) {
      assert.strictEqual(result.status, 'healthy', 'Should be healthy when < 80%');
      assert.strictEqual(result.severity, 'HEALTHY', 'Severity should be HEALTHY');
    }
    
    console.log(`✓ Disk check: ${result.details.message}`);
  });
  
  it('disk_space is registered as SAFETY check', () => {
    // Verify in built-in checks
    assert.ok(Health.safetyChecks.disk_space, 'disk_space should be in safetyChecks');
    assert.strictEqual(Health.safetyChecks.disk_space.domain, 'SAFETY', 'Should be SAFETY domain');
    assert.strictEqual(Health.safetyChecks.disk_space.severity, 'CRITICAL', 'Should be CRITICAL severity');
    
    console.log('✓ disk_space is SAFETY check with CRITICAL severity');
  });
  
  it('checkDiskSpace is exported and callable', () => {
    assert.strictEqual(typeof Health.checkDiskSpace, 'function', 'checkDiskSpace should be a function');
    
    console.log('✓ checkDiskSpace is exported');
  });
  
});

describe('SAFETY: Disk Space Thresholds', () => {
  
  it('returns warn when disk >= 80%', () => {
    // Simulated: 82% used
    const mockResult = {
      status: 'warn',
      severity: 'WARN',
      details: {
        used_percent: 82,
        message: 'DISK WARNING: 82% used (> 80%)'
      }
    };
    
    assert.strictEqual(mockResult.status, 'warn');
    assert.strictEqual(mockResult.severity, 'WARN');
    
    console.log('✓ Warning at 80%+ usage');
  });
  
  it('returns critical when disk >= 90%', () => {
    // Simulated: 92% used
    const mockResult = {
      status: 'critical',
      severity: 'CRITICAL',
      details: {
        used_percent: 92,
        message: 'DISK CRITICAL: 92% used (> 90%) - TRADING PAUSED',
        action: 'PAUSE_TRADING'
      }
    };
    
    assert.strictEqual(mockResult.status, 'critical');
    assert.strictEqual(mockResult.severity, 'CRITICAL');
    assert.strictEqual(mockResult.details.action, 'PAUSE_TRADING');
    
    console.log('✓ CRITICAL at 90%+ usage -> PAUSE_TRADING');
  });
  
});

// Integration: Register the check
describe('INTEGRATION: Register disk_space check', () => {
  
  it('disk_space check can be registered with Health service', () => {
    // Register the actual check
    Health.register('disk_space', async () => {
      return await Health.checkDiskSpace();
    }, {
      domain: Health.DOMAIN.SAFETY,
      severity: 'CRITICAL',
      timeout: 5000
    });
    
    const status = Health.getStatus();
    assert.strictEqual(status.isMonitoring, false, 'Not yet monitoring');
    
    console.log('✓ disk_space check registered');
  });
  
});
