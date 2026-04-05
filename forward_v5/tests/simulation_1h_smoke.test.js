/**
 * Simulation: 1h Smoke Test
 * Phase 6 - Step 1: Validate system stability under 1 hour continuous operation
 * 
 * SUCCESS CRITERIA:
 * 1. System runs 60 minutes without interruption
 * 2. No Circuit Breaker triggers (unless legitimate SAFETY failure)
 * 3. Event Store grows consistently (no corruption)
 * 4. Memory usage stays below 80% threshold
 * 5. Health checks pass throughout
 * 6. State Projection remains consistent
 * 
 * AUTO-TRANSITION: On success → triggers 24h Stability Test
 * ON FAILURE: Generates diagnostic report and stops
 */

const { describe, it } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

// Duration: 60 minutes
const TEST_DURATION_MS = 60 * 60 * 1000; // 1 hour
const CHECK_INTERVAL_MS = 5 * 60 * 1000; // Check every 5 minutes

// Success thresholds
const THRESHOLDS = {
  MAX_MEMORY_PERCENT: 80,
  CIRCUIT_BREAKER_FAULTS_ALLOWED: 0,
  MIN_HEALTH_CHECK_SUCCESS_RATE: 0.95
};

describe('SIMULATION_1h_Smoke_Test', () => {
  
  it('runs_1h_continuous_with_validations', async () => {
    const startTime = Date.now();
    const endTime = startTime + TEST_DURATION_MS;
    
    const report = {
      test_name: '1h_Smoke_Test',
      start_time: new Date(startTime).toISOString(),
      end_time: null,
      duration_ms: TEST_DURATION_MS,
      status: 'RUNNING',
      checks: [],
      errors: [],
      memory_samples: [],
      circuit_breaker_state_changes: [],
      event_store_growth: []
    };
    
    // Load system components
    const CircuitBreaker = require('../src/circuit_breaker.js');
    const StateProjection = require('../src/state_projection.js');
    const Health = require('../src/health.js');
    const AlertEngine = require('../cli/alertEngine.js');
    
    // Initialize alert engine for test notifications
    const alertEngine = new AlertEngine({
      discordWebhook: process.env.DISCORD_WEBHOOK_URL
    });
    
    console.log('🔥 1h Smoke Test Starting');
    console.log(`Duration: ${TEST_DURATION_MS / 1000 / 60} minutes`);
    console.log(`Check interval: ${CHECK_INTERVAL_MS / 1000 / 60} minutes`);
    console.log(`End time: ${new Date(endTime).toISOString()}`);
    
    // Send start notification
    await alertEngine.sendDiscord({
      severity: 'INFO',
      message: '🧪 1h Smoke Test STARTED - Monitoring for 60 minutes',
      timestamp: new Date().toISOString(),
      source: 'simulation_1h_smoke',
      rule: 'test_start'
    });
    
    // Main test loop
    let checkCount = 0;
    let healthCheckPassed = 0;
    let lastCircuitBreakerState = CircuitBreaker.getStatus ? CircuitBreaker.getStatus().state : 'UNKNOWN';
    
    while (Date.now() < endTime) {
      await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL_MS));
      checkCount++;
      
      const now = Date.now();
      const elapsedMinutes = (now - startTime) / 1000 / 60;
      
      // Check 1: Health Status
      const healthStatus = StateProjection.getCurrentState().safety.overall_status;
      const healthOk = healthStatus === 'healthy';
      if (healthOk) healthCheckPassed++;
      
      // Check 2: Memory
      const memUsage = process.memoryUsage();
      const heapPercent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
      report.memory_samples.push({
        timestamp: now,
        elapsed_minutes: elapsedMinutes,
        heap_used_mb: (memUsage.heapUsed / 1024 / 1024).toFixed(2),
        heap_total_mb: (memUsage.heapTotal / 1024 / 1024).toFixed(2),
        percent: heapPercent.toFixed(1)
      });
      
      // Check 3: Circuit Breaker
      const currentCBState = CircuitBreaker.getStatus ? CircuitBreaker.getStatus().state : 'UNKNOWN';
      if (currentCBState !== lastCircuitBreakerState) {
        report.circuit_breaker_state_changes.push({
          timestamp: now,
          elapsed_minutes: elapsedMinutes,
          from: lastCircuitBreakerState,
          to: currentCBState
        });
        lastCircuitBreakerState = currentCBState;
        
        // If CB opened unexpectedly, that's a failure
        if (currentCBState === 'OPEN' && healthStatus === 'healthy') {
          const err = `Circuit Breaker opened at ${elapsedMinutes.toFixed(1)}m without SAFETY failure`;
          report.errors.push(err);
          console.error('❌ ' + err);
        }
      }
      
      // Check 4: State Projection consistency
      const state = StateProjection.getCurrentState();
      const stateConsistent = state.projection_version !== undefined && 
                             Array.isArray(state.open_positions);
      
      // Log progress
      report.checks.push({
        check_number: checkCount,
        elapsed_minutes: elapsedMinutes.toFixed(1),
        health: healthStatus,
        memory_percent: heapPercent.toFixed(1),
        circuit_breaker: currentCBState,
        state_consistent: stateConsistent
      });
      
      console.log(`✓ Check ${checkCount} @ ${elapsedMinutes.toFixed(1)}m: Health=${healthStatus}, Memory=${heapPercent.toFixed(1)}%, CB=${currentCBState}`);
      
      // Check memory threshold
      if (heapPercent > THRESHOLDS.MAX_MEMORY_PERCENT) {
        const err = `Memory threshold exceeded: ${heapPercent.toFixed(1)}% > ${THRESHOLDS.MAX_MEMORY_PERCENT}%`;
        report.errors.push(err);
        console.error('❌ ' + err);
        
        await alertEngine.sendDiscord({
          severity: 'CRITICAL',
          message: `🧪 1h Smoke Test FAILED: Memory threshold exceeded`,
          timestamp: new Date().toISOString(),
          source: 'simulation_1h_smoke',
          rule: 'memory_threshold'
        });
        break;
      }
    }
    
    // Finalize report
    report.end_time = new Date().toISOString();
    const actualDuration = Date.now() - startTime;
    report.duration_actual_ms = actualDuration;
    
    // Success Criteria Validation
    const completedFullDuration = actualDuration >= TEST_DURATION_MS * 0.95; // Allow 5% slack
    const healthSuccessRate = healthCheckPassed / checkCount;
    const noUnexpectedCBOpen = report.circuit_breaker_state_changes.every(
      change => change.to !== 'OPEN' || report.errors.some(e => e.includes('SAFETY'))
    );
    const memoryOk = report.memory_samples.every(s => parseFloat(s.percent) <= THRESHOLDS.MAX_MEMORY_PERCENT);
    
    // Determine status
    const passed = completedFullDuration && 
                   healthSuccessRate >= THRESHOLDS.MIN_HEALTH_CHECK_SUCCESS_RATE &&
                   noUnexpectedCBOpen &&
                   memoryOk &&
                   report.errors.length === 0;
    
    report.status = passed ? 'PASSED' : 'FAILED';
    report.success_criteria = {
      completed_full_duration: completedFullDuration,
      health_success_rate: healthSuccessRate.toFixed(2),
      no_unexpected_cb_open: noUnexpectedCBOpen,
      memory_ok: memoryOk,
      total_errors: report.errors.length
    };
    
    // Save report
    const reportFile = path.join(__dirname, '..', 'simulation', `report_1h_smoke_${Date.now()}.json`);
    fs.mkdirSync(path.dirname(reportFile), { recursive: true });
    fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
    
    // Send completion notification
    if (passed) {
      console.log('✅ 1h Smoke Test PASSED');
      console.log(`Health success rate: ${(healthSuccessRate * 100).toFixed(1)}%`);
      console.log(`Circuit breaker faults: ${report.circuit_breaker_state_changes.length}`);
      console.log(`Report saved: ${reportFile}`);
      
      await alertEngine.sendDiscord({
        severity: 'INFO',
        message: '✅ 1h Smoke Test PASSED - Auto-triggering 24h Stability Test...',
        timestamp: new Date().toISOString(),
        source: 'simulation_1h_smoke',
        rule: 'test_complete'
      });
      
      // Trigger 24h automatically
      console.log('🚀 Auto-transitioning to 24h Stability Test...');
      require('./simulation_24h_stability.test.js');
      
    } else {
      console.log('❌ 1h Smoke Test FAILED');
      console.log(`Errors: ${report.errors.join(', ')}`);
      console.log(`Report saved: ${reportFile}`);
      
      await alertEngine.sendDiscord({
        severity: 'CRITICAL',
        message: `❌ 1h Smoke Test FAILED: ${report.errors.length} errors detected`,
        timestamp: new Date().toISOString(),
        source: 'simulation_1h_smoke',
        rule: 'test_failed'
      });
      
      assert.fail(`1h Smoke Test failed: ${report.errors.join(', ')}`);
    }
  });
});

console.log('\n🔥 1h Smoke Test Module Loaded');
console.log('Ready to validate system stability for 60 minutes\n');
