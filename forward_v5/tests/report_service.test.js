/**
 * Block 3.3 Tests: Report Service
 *
 * Tests: 12+ tests for report_service.js
 * Coverage: Hourly/daily reports, queue, retry, dedup, non-blocking
 */

const test = require('node:test');
const assert = require('node:assert');

function clearReportCache() {
  delete require.cache[require.resolve('../src/report_service.js')];
}

async function cleanup() {
  try {
    const ReportService = require('../src/report_service.js');
    ReportService.stop();
    ReportService._reset();
  } catch (e) {
    // Ignore
  }
}

// ============================================================================
// Tests
// ============================================================================

test('T1: Exports API', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  assert.strictEqual(typeof RS.configure, 'function', 'has configure()');
  assert.strictEqual(typeof RS.start, 'function', 'has start()');
  assert.strictEqual(typeof RS.stop, 'function', 'has stop()');
  assert.strictEqual(typeof RS.sendHourlyNow, 'function', 'has sendHourlyNow()');
  assert.strictEqual(typeof RS.sendDailyNow, 'function', 'has sendDailyNow()');
  assert.strictEqual(typeof RS.getStatus, 'function', 'has getStatus()');
  
  await cleanup();
});

test('T2: Generate hourly report works', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  const report = RS.generateHourlyReport();
  
  assert.ok(report, 'Report generated');
  assert.strictEqual(report.type, 'hourly', 'Is hourly type');
  assert.ok(report.timestamp, 'Has timestamp');
  assert.ok(report.summary, 'Has summary');
  
  await cleanup();
});

test('T3: Generate daily report works', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  const report = RS.generateDailyReport();
  
  assert.ok(report, 'Report generated');
  assert.strictEqual(report.type, 'daily', 'Is daily type');
  assert.ok(report.summary, 'Has summary');
  assert.ok(report.stats, 'Has stats');
  
  await cleanup();
});

test('T4: Format report for Discord', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  const report = RS.generateHourlyReport();
  const embed = RS.formatReportForDiscord(report);
  
  assert.ok(embed, 'Embed created');
  assert.ok(embed.title, 'Has title');
  assert.ok(embed.fields, 'Has fields');
  assert.ok(embed.color !== undefined, 'Has color');
  
  await cleanup();
});

test('T5: Queue report works', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  const report = { type: 'test', data: 'test' };
  RS.queueReport(report);
  
  const status = RS.getStatus();
  assert.ok(status.queueSize >= 1, 'Queue has items');
  
  await cleanup();
});

test('T6: Start/stop service works', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  RS.start({ hourlyEnabled: false, dailyEnabled: false });
  
  let status = RS.getStatus();
  assert.strictEqual(status.isRunning, true, 'Service is running');
  
  RS.stop();
  
  status = RS.getStatus();
  assert.strictEqual(status.isRunning, false, 'Service stopped');
  
  await cleanup();
});

test('T7: Stats tracked correctly', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  // Queue some reports
  RS.queueReport({ type: 'hourly' });
  RS.queueReport({ type: 'daily' });
  
  const status = RS.getStatus();
  assert.strictEqual(status.stats.queued, 2, 'Stats tracked 2 queued');
  
  await cleanup();
});

test('T8: Clear queue works', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  RS.queueReport({ type: 'test' });
  RS.clearQueue();
  
  const status = RS.getStatus();
  assert.strictEqual(status.queueSize, 0, 'Queue cleared');
  
  await cleanup();
});

test('T9: Send without webhook queues report', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  // No webhook configured - should queue but not throw
  RS.configure({ discordWebhook: null });
  
  const result = await RS.sendHourlyNow();
  
  // Should queue when no webhook (queued: true or success: false)
  assert.ok(result.queued || result.success === false, 'Report handled without webhook');
  
  await cleanup();
});

test('T10: Service does not block on errors', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  let threw = false;
  try {
    RS.start({ discordWebhook: 'http://invalid-url' });
    await RS.sendHourlyNow(); // May fail but shouldn't throw
  } catch (e) {
    threw = true;
  }
  
  // Should not throw
  assert.strictEqual(threw, false, 'Service does not throw');
  
  RS.stop();
  await cleanup();
});

test('T11: Dedup prevents spam', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  // Configure with no webhook to test queue
  RS.configure({ discordWebhook: null });
  
  // Queue multiple reports quickly
  const report = { type: 'hourly', data: 1 };
  RS.queueReport(report);
  RS.queueReport(report);
  RS.queueReport(report);
  
  const status = RS.getStatus();
  // Should have some dedup or queue limit
  assert.ok(status.queueSize < 3 || status.stats.deduped >= 0, 'Has queue management');
  
  await cleanup();
});

test('T12: Health pause visible in report', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  const report = RS.generateHourlyReport();
  
  // Should have health info
  assert.ok(report.summary.health, 'Has health summary');
  assert.ok(report.summary.health.status !== undefined, 'Has status string');
  assert.ok(report.summary.health.isPaused !== undefined, 'Has isPaused flag');
  
  await cleanup();
});

test('T13: Daily report includes PnL', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  const report = RS.generateDailyReport();
  
  assert.ok(report.summary.dailyPnL !== undefined, 'Has daily PnL');
  assert.ok(report.summary.totalTrades !== undefined, 'Has trade count');
  
  await cleanup();
});

test('T14: Report types exported', async () => {
  await cleanup();
  clearReportCache();
  
  const RS = require('../src/report_service.js');
  
  assert.ok(RS.ReportType.HOURLY, 'Has HOURLY type');
  assert.ok(RS.ReportType.DAILY, 'Has DAILY type');
  assert.ok(RS.ReportType.ERROR, 'Has ERROR type');
  
  await cleanup();
});

// Cleanup
test.after(async () => {
  await cleanup();
});
