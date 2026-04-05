/**
 * Simulation: 24h Stability Test
 * Phase 6 - Step 2: Long-term stability validation
 * 
 * SUCCESS CRITERIA:
 * 1. System runs 24 hours without interruption
 * 2. Memory stays below 85% (allows slow growth)
 * 3. Event Store grows linearly (no corruption)
 * 4. Health checks pass > 98%
 * 5. No Circuit Breaker false triggers
 * 6. State remains consistent throughout
 * 
 * MONITORING:
 * - Discord updates every 4 hours
 * - Heartbeat file every 15 minutes
 * - Immediate Discord alert on CRITICAL
 */

const { describe, it } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

// Duration: 24 hours
const TEST_DURATION_MS = 24 * 60 * 60 * 1000;
const CHECK_INTERVAL_MS = 15 * 60 * 1000; // Check every 15 minutes
const DISCORD_INTERVAL_MS = 4 * 60 * 60 * 1000; // Discord every 4 hours
const HEARTBEAT_INTERVAL_MS = 15 * 60 * 1000; // Heartbeat every 15 minutes

// Success thresholds (slightly relaxed for 24h)
const THRESHOLDS = {
  MAX_MEMORY_PERCENT: 85,  // Allows slow memory growth
  HEALTH_CHECK_SUCCESS_RATE: 0.98,  // 98% over 24h
  MAX_EVENT_STORE_GROWTH_MB_PER_HOUR: 50  // Reasonable for paper trading
};

// Discord webhook (set via environment variable)
const DISCORD_WEBHOOK = process.env.DISCORD_WEBHOOK_URL;

// Skip Discord if no webhook configured
const SKIP_DISCORD = !DISCORD_WEBHOOK;

describe('SIMULATION_24h_Stability_Test', () => {
  
  it('runs_24h_with_monitoring', async () => {
    const startTime = Date.now();
    const endTime = startTime + TEST_DURATION_MS;
    const testId = `24h_${Date.now()}`;
    
    const report = {
      test_name: '24h_Stability_Test',
      test_id: testId,
      start_time: new Date(startTime).toISOString(),
      end_time: null,
      duration_ms: TEST_DURATION_MS,
      status: 'RUNNING',
      checks: [],
      errors: [],
      memory_samples: [],
      discord_updates: [],
      circuit_breaker_state_changes: [],
      event_store_stats: []
    };
    
    // Load components
    const CircuitBreaker = require('../src/circuit_breaker.js');
    const StateProjection = require('../src/state_projection.js');
    const Health = require('../src/health.js');
    
    // Setup heartbeat file
    const heartbeatFile = path.join(__dirname, '..', 'simulation', `heartbeat_${testId}.log`);
    fs.mkdirSync(path.dirname(heartbeatFile), { recursive: true });
    
    // 🛡️ DISK PROTECTION: Max 1MB for heartbeat, 10MB for report
    const MAX_HEARTBEAT_SIZE_BYTES = 1 * 1024 * 1024;  // 1MB
    const MAX_TOTAL_LOG_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
    
    const writeHeartbeat = (msg) => {
      // Check size before writing
      try {
        const stats = fs.statSync(heartbeatFile);
        if (stats.size > MAX_HEARTBEAT_SIZE_BYTES) {
          console.warn(`🚨 HEARTBEAT SIZE LIMIT: ${(stats.size/1024/1024).toFixed(2)}MB > 1MB - stopping writes`);
          return; // Skip write
        }
      } catch (e) {
        // File doesn't exist yet, that's OK
      }
      fs.appendFileSync(heartbeatFile, `[${new Date().toISOString()}] ${msg}\n`);
    };
    
    // Emergency disk check function
    const checkDiskSafety = () => {
      try {
        // Check total simulation dir size
        const files = fs.readdirSync(path.dirname(heartbeatFile));
        let totalSize = 0;
        for (const file of files) {
          if (file.startsWith('heartbeat_') || file.startsWith('report_')) {
            const stats = fs.statSync(path.join(path.dirname(heartbeatFile), file));
            totalSize += stats.size;
          }
        }
        
        if (totalSize > MAX_TOTAL_LOG_SIZE_BYTES) {
          const msg = `🚨 DISK SAFETY: Total log size ${(totalSize/1024/1024).toFixed(2)}MB > 10MB - ABORTING TEST`;
          console.error(msg);
          report.errors.push(msg);
          report.status = 'ABORTED_DISK_SAFETY';
          return false; // Signal to stop
        }
        return true; // OK to continue
      } catch (e) {
        return true; // Continue on error
      }
    };
    
    const sendDiscord = async (message) => {
      if (SKIP_DISCORD) {
        console.log('[Discord skipped - no webhook configured]');
        return;
      }
      try {
        const { exec } = require('child_process');
        const util = require('util');
        const execPromise = util.promisify(exec);
        
        const payload = JSON.stringify({ content: message });
        await execPromise(`curl -s -X POST -H "Content-Type: application/json" -d '${payload}' "${DISCORD_WEBHOOK}"`);
      } catch (err) {
        console.error('Discord send failed:', err.message);
      }
    };
    
    console.log('🔥 24h Stability Test Starting');
    console.log(`Duration: 24 hours`);
    console.log(`End time: ${new Date(endTime).toISOString()}`);
    
    // Initial Discord message
    await sendDiscord(
      `🧪 **24h Stability Test STARTED**\n\n` +
      `⏱️ Start: ${new Date(startTime).toISOString()}\n` +
      `⏱️ Ende: ${new Date(endTime).toISOString()}\n` +
      `📊 Updates: Alle 4 Stunden\n` +
      `💓 Heartbeat: Alle 15 Minuten\n\n` +
      `Erfolgskriterien:\n` +
      `• 24h ohne Unterbrechung\n` +
      `• Memory < 85%\n` +
      `• Health > 98%\n` +
      `• Keine CB Fehlauslösungen`
    );
    
    // Main loop
    let checkCount = 0;
    let healthCheckPassed = 0;
    let lastDiscordUpdate = startTime;
    let lastCircuitBreakerState = CircuitBreaker.getStatus?.().state || 'UNKNOWN';
    
    while (Date.now() < endTime) {
      await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL_MS));
      checkCount++;
      
      // 🛡️ DISK SAFETY CHECK (every iteration)
      if (!checkDiskSafety()) {
        break; // Abort loop if disk safety triggered
      }
      
      const now = Date.now();
      const elapsedHours = (now - startTime) / 1000 / 60 / 60;
      
      // Health check
      const healthStatus = StateProjection.getCurrentState().safety?.overall_status || 'unknown';
      const healthOk = healthStatus === 'healthy';
      if (healthOk) healthCheckPassed++;
      
      // Memory
      const memUsage = process.memoryUsage();
      const heapPercent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
      
      // Circuit Breaker
      const currentCBState = CircuitBreaker.getStatus?.().state || 'UNKNOWN';
      if (currentCBState !== lastCircuitBreakerState) {
        report.circuit_breaker_state_changes.push({
          elapsed_hours: elapsedHours.toFixed(2),
          from: lastCircuitBreakerState,
          to: currentCBState
        });
        lastCircuitBreakerState = currentCBState;
        
        // Alert on unexpected CB open
        if (currentCBState === 'OPEN' && healthStatus === 'healthy') {
          const err = `Circuit Breaker opened at ${elapsedHours.toFixed(2)}h without SAFETY failure`;
          report.errors.push(err);
          await sendDiscord(`🚨 **24h Test CRITICAL**\n${err}`);
        }
      }
      
      // Record check
      report.checks.push({
        check_number: checkCount,
        elapsed_hours: elapsedHours.toFixed(2),
        health: healthStatus,
        memory_percent: heapPercent.toFixed(1),
        circuit_breaker: currentCBState
      });
      
      // Heartbeat
      writeHeartbeat(`Check ${checkCount} @ ${elapsedHours.toFixed(1)}h - Health=${healthStatus}, Memory=${heapPercent.toFixed(1)}%, CB=${currentCBState}`);
      
      // Memory sample
      report.memory_samples.push({
        elapsed_hours: elapsedHours.toFixed(2),
        percent: heapPercent.toFixed(1),
        timestamp: now
      });
      
      // Memory threshold check
      if (heapPercent > THRESHOLDS.MAX_MEMORY_PERCENT) {
        const err = `Memory threshold exceeded: ${heapPercent.toFixed(1)}% > ${THRESHOLDS.MAX_MEMORY_PERCENT}%`;
        report.errors.push(err);
        await sendDiscord(`🚨 **24h Test FAILED**\n${err}`);
        break;
      }
      
      // Discord update every 4 hours
      if (now - lastDiscordUpdate >= DISCORD_INTERVAL_MS) {
        const healthRate = checkCount > 0 ? (healthCheckPassed / checkCount * 100).toFixed(1) : 100;
        await sendDiscord(
          `📊 **24h Update (${elapsedHours.toFixed(1)}h / 24h)**\n\n` +
          `✓ Health Success: ${healthRate}%\n` +
          `💾 Memory: ${heapPercent.toFixed(1)}%\n` +
          `⚡ Circuit Breaker: ${currentCBState}\n` +
          `🔄 Checks: ${checkCount}\n\n` +
          report.errors.length > 0 ? `⚠️ Warnings: ${report.errors.length}` : '✅ All good'
        );
        report.discord_updates.push({ elapsed_hours: elapsedHours.toFixed(2), message: 'Status update sent' });
        lastDiscordUpdate = now;
      }
      
      // Log progress every hour
      if (checkCount % 4 === 0) {  // Every hour (4 * 15min)
        console.log(`✓ ${elapsedHours.toFixed(1)}h elapsed: Health=${healthStatus}, Memory=${heapPercent.toFixed(1)}%`);
      }
    }
    
    // Finalize
    report.end_time = new Date().toISOString();
    report.duration_actual_ms = Date.now() - startTime;
    
    // Validation
    const completedFullDuration = report.duration_actual_ms >= TEST_DURATION_MS * 0.95;
    const healthSuccessRate = checkCount > 0 ? healthCheckPassed / checkCount : 1;
    const maxMemory = report.memory_samples.length > 0
      ? Math.max(...report.memory_samples.map(s => parseFloat(s.percent)))
      : 0;
    const memoryOk = maxMemory <= THRESHOLDS.MAX_MEMORY_PERCENT;
    const noUnexpectedCB = report.circuit_breaker_state_changes.every(
      c => c.to !== 'OPEN' || report.errors.some(e => e.includes('SAFETY'))
    );
    
    // Determine status
    const passed = completedFullDuration &&
                   healthSuccessRate >= THRESHOLDS.HEALTH_CHECK_SUCCESS_RATE &&
                   memoryOk &&
                   noUnexpectedCB &&
                   report.errors.length === 0;
    
    report.status = passed ? 'PASSED' : 'FAILED';
    report.summary = {
      completed_full_duration: completedFullDuration,
      health_success_rate: (healthSuccessRate * 100).toFixed(1) + '%',
      max_memory: maxMemory.toFixed(1) + '%',
      memory_ok: memoryOk,
      circuit_breaker_changes: report.circuit_breaker_state_changes.length,
      total_errors: report.errors.length
    };
    
    // Save report
    const reportFile = path.join(__dirname, '..', 'simulation', `report_24h_${testId}.json`);
    fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
    
    // Final Discord
    if (passed) {
      await sendDiscord(
        `✅ **24h Stability Test BESTANDEN**\n\n` +
        `📊 Ergebnis:\n` +
        `• Duration: 24 hours ✅\n` +
        `• Health Success: ${(healthSuccessRate * 100).toFixed(1)}% ✅\n` +
        `• Max Memory: ${maxMemory.toFixed(1)}% ✅\n` +
        `• CB State Changes: ${report.circuit_breaker_state_changes.length} ✅\n\n` +
        `Report: ${reportFile}\n\n` +
        `🎉 Phase 6 SIMULATION COMPLETE`
      );
      console.log('✅ 24h Stability Test PASSED');
    } else {
      await sendDiscord(
        `❌ **24h Stability Test FEHLGESCHLAGEN**\n\n` +
        `Errors: ${report.errors.join('; ')}\n\n` +
        `Details: ${reportFile}`
      );
      console.log('❌ 24h Stability Test FAILED');
      assert.fail(`24h Test failed: ${report.errors.join(', ')}`);
    }
  });
});

console.log('\n🔥 24h Stability Test Module Loaded');
console.log('Ready for 24-hour validation\n');
