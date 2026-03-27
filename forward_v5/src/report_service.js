/**
 * Block 3.3: Report Service
 *
 * Periodic Discord reports as non-blocking Observability component.
 *
 * Reports:
 * - Hourly: Positions, PnL, Trades, Health status
 * - Daily: Full session recap, aggregated metrics
 *
 * Robustness:
 * - Queue on Discord/Webhook failure
 * - Retry with exponential backoff
 * - Dedup against spam
 * - WARN + Log on send failures
 * - NEVER blocks trading
 *
 * @module report_service
 * @version 1.0.0
 */

const Logger = require('./logger.js');
const EventStore = require('./event_store.js');
const StateProjection = require('./state_projection.js');
const Health = require('./health.js');

// ============================================================================
// Configuration
// ============================================================================

const DEFAULT_HOURLY_MINUTE = 0;   // Top of each hour
const DEFAULT_DAILY_HOUR = 9;      // 9 AM daily
const MAX_QUEUE_SIZE = 100;
const RETRY_DELAYS = [5000, 15000, 30000, 60000]; // Exponential backoff: 5s, 15s, 30s, 60s
const SPAM_COOLDOWN_MS = 300000; // 5 minutes between same report type

// ============================================================================
// State
// ============================================================================

let config = {
  discordWebhook: null,
  hourlyEnabled: true,
  dailyEnabled: true,
  hourlyMinute: DEFAULT_HOURLY_MINUTE,
  dailyHour: DEFAULT_DAILY_HOUR
};

let isRunning = false;
let hourlyInterval = null;
let dailyInterval = null;
let processQueueInterval = null;

// Queue for failed reports
const reportQueue = [];

// Dedup tracking
const lastSentTimes = new Map();

// Stats
let stats = {
  sent: 0,
  queued: 0,
  failed: 0,
  deduped: 0
};

// ============================================================================
// Report Types
// ============================================================================

const ReportType = {
  HOURLY: 'hourly',
  DAILY: 'daily',
  ERROR: 'error'
};

// ============================================================================
// Report Generation
// ============================================================================

/**
 * Generate hourly report
 */
function generateHourlyReport() {
  const state = StateProjection.getCurrentState ? StateProjection.getCurrentState() : {};
  const healthStatus = Health.getStatus ? Health.getStatus() : {};
  
  // Get last hour's events
  const hourAgo = new Date(Date.now() - 3600000).toISOString();
  let recentEvents = [];
  try {
    if (EventStore.getEvents) {
      recentEvents = EventStore.getEvents({ 
        since: hourAgo, 
        limit: 100 
      }).events || [];
    }
  } catch (e) {
    // Non-blocking: ignore errors
  }
  
  const trades = recentEvents.filter(e => 
    e.event_type === 'TRADE_EXECUTED' || 
    e.event_type === 'POSITION_OPENED' ||
    e.event_type === 'POSITION_CLOSED'
  );
  
  return {
    type: ReportType.HOURLY,
    timestamp: new Date().toISOString(),
    period: '1h',
    summary: {
      positions: Object.keys(state.positions || {}).length,
      pnl: calculatePnL(state),
      trades: trades.length,
      health: {
        status: healthStatus.isPaused ? '⏸️ PAUSED' : '✅ RUNNING',
        isPaused: healthStatus.isPaused || false,
        monitoring: healthStatus.isMonitoring || false
      }
    },
    details: {
      openPositions: Object.entries(state.positions || {}).map(([id, pos]) => ({
        id,
        symbol: pos.symbol,
        side: pos.side,
        size: pos.size,
        entryPrice: pos.entry_price,
        pnl: pos.unrealized_pnl
      })),
      recentTrades: trades.slice(-5).map(t => ({
        type: t.event_type,
        symbol: t.payload?.symbol,
        time: t.occurred_at
      }))
    }
  };
}

/**
 * Generate daily report
 */
function generateDailyReport() {
  const state = StateProjection.getCurrentState ? StateProjection.getCurrentState() : {};
  const healthStatus = Health.getStatus ? Health.getStatus() : {};
  
  // Get last 24h events
  const dayAgo = new Date(Date.now() - 86400000).toISOString();
  let dayEvents = [];
  try {
    if (EventStore.getEvents) {
      dayEvents = EventStore.getEvents({ 
        since: dayAgo, 
        limit: 1000 
      }).events || [];
    }
  } catch (e) {
    // Non-blocking
  }
  
  const trades = dayEvents.filter(e => 
    e.event_type === 'TRADE_EXECUTED' || 
    e.event_type === 'POSITION_OPENED' ||
    e.event_type === 'POSITION_CLOSED'
  );
  
  const errors = dayEvents.filter(e => 
    e.event_type === 'ERROR' || 
    e.event_type === 'HEALTH_SAFETY_FAILED'
  );
  
  return {
    type: ReportType.DAILY,
    timestamp: new Date().toISOString(),
    period: '24h',
    summary: {
      totalTrades: trades.length,
      totalErrors: errors.length,
      finalPositions: Object.keys(state.positions || {}).length,
      dailyPnL: calculateDailyPnL(dayEvents),
      healthStatus: healthStatus.isPaused ? '⏸️ PAUSED' : '✅ RUNNING'
    },
    stats: {
      ...stats,
      queueSize: reportQueue.length
    }
  };
}

/**
 * Generate error report
 */
function generateErrorReport(error) {
  return {
    type: ReportType.ERROR,
    timestamp: new Date().toISOString(),
    error: {
      message: error.message,
      stack: error.stack?.substring(0, 500)
    },
    context: {
      queueSize: reportQueue.length,
      stats: { ...stats }
    }
  };
}

// PnL calculation helpers
function calculatePnL(state) {
  let total = 0;
  for (const pos of Object.values(state.positions || {})) {
    total += pos.unrealized_pnl || 0;
  }
  return total;
}

function calculateDailyPnL(events) {
  let total = 0;
  for (const evt of events) {
    if (evt.event_type === 'POSITION_CLOSED' && evt.payload?.realized_pnl) {
      total += evt.payload.realized_pnl;
    }
  }
  return total;
}

// ============================================================================
// Discord Integration
// ============================================================================

/**
 * Send report to Discord with queue fallback
 */
async function sendReport(report) {
  if (!config.discordWebhook) {
    Logger.warn('Discord webhook not configured, queuing report', { 
      module: 'report_service',
      reportType: report.type 
    });
    queueReport(report);
    return { success: false, queued: true, reason: 'no_webhook' };
  }
  
  // Dedup check
  const now = Date.now();
  const lastSent = lastSentTimes.get(report.type) || 0;
  if (now - lastSent < SPAM_COOLDOWN_MS && report.type !== ReportType.ERROR) {
    Logger.debug(`Report ${report.type} deduped (cooldown)`, { module: 'report_service' });
    stats.deduped++;
    return { success: false, deduped: true };
  }
  
  const embed = formatReportForDiscord(report);
  
  try {
    const response = await fetch(config.discordWebhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ embeds: [embed] })
    });
    
    if (!response.ok) {
      throw new Error(`Discord returned ${response.status}`);
    }
    
    lastSentTimes.set(report.type, now);
    stats.sent++;
    
    Logger.info(`Report sent: ${report.type}`, { module: 'report_service' });
    return { success: true };
    
  } catch (err) {
    // Non-blocking: queue and retry
    Logger.warn(`Discord send failed, queuing: ${err.message}`, { 
      module: 'report_service',
      reportType: report.type 
    });
    
    queueReport(report);
    return { success: false, queued: true, error: err.message };
  }
}

/**
 * Format report for Discord embed
 */
function formatReportForDiscord(report) {
  switch (report.type) {
    case ReportType.HOURLY:
      return {
        title: '📊 Hourly Trading Report',
        color: report.summary.health.isPaused ? 0xff0000 : 0x00ff00,
        timestamp: report.timestamp,
        fields: [
          {
            name: '📈 Positions',
            value: `${report.summary.positions} open`,
            inline: true
          },
          {
            name: '💰 PnL',
            value: `${report.summary.pnl > 0 ? '+' : ''}${report.summary.pnl.toFixed(2)}`,
            inline: true
          },
          {
            name: '🔄 Trades (1h)',
            value: `${report.summary.trades}`,
            inline: true
          },
          {
            name: '🏥 Health',
            value: report.summary.health.status,
            inline: false
          }
        ]
      };
      
    case ReportType.DAILY:
      return {
        title: '📈 Daily Session Recap',
        color: 0x0099ff,
        timestamp: report.timestamp,
        fields: [
          {
            name: '💹 Total Trades',
            value: `${report.summary.totalTrades}`,
            inline: true
          },
          {
            name: '📊 Daily PnL',
            value: `${report.summary.dailyPnL > 0 ? '+' : ''}${report.summary.dailyPnL.toFixed(2)}`,
            inline: true
          },
          {
            name: '❌ Errors',
            value: `${report.summary.totalErrors}`,
            inline: true
          },
          {
            name: '🏥 Status',
            value: report.summary.healthStatus,
            inline: false
          }
        ]
      };
      
    case ReportType.ERROR:
      return {
        title: '⚠️ Report Service Error',
        color: 0xffaa00,
        timestamp: report.timestamp,
        description: report.error.message.substring(0, 1000)
      };
      
    default:
      return {
        title: '📋 Report',
        color: 0x888888,
        timestamp: report.timestamp
      };
  }
}

// ============================================================================
// Queue Management
// ============================================================================

/**
 * Queue report for retry
 */
function queueReport(report) {
  if (reportQueue.length >= MAX_QUEUE_SIZE) {
    Logger.error('Report queue full, dropping oldest', { module: 'report_service' });
    reportQueue.shift(); // Remove oldest
  }
  
  reportQueue.push({
    ...report,
    queuedAt: Date.now(),
    retryCount: 0
  });
  
  stats.queued++;
  Logger.debug(`Report queued: ${report.type} (queue: ${reportQueue.length})`, { 
    module: 'report_service' 
  });
}

/**
 * Process queued reports with retry
 */
async function processQueue() {
  if (reportQueue.length === 0) return;
  if (!config.discordWebhook) return;
  
  const item = reportQueue[0];
  const delay = RETRY_DELAYS[Math.min(item.retryCount, RETRY_DELAYS.length - 1)];
  
  if (Date.now() - item.queuedAt < delay) {
    return; // Wait for backoff
  }
  
  try {
    const response = await fetch(config.discordWebhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ embeds: [formatReportForDiscord(item)] })
    });
    
    if (response.ok) {
      reportQueue.shift(); // Remove sent item
      stats.sent++;
      Logger.info(`Queued report sent: ${item.type}`, { module: 'report_service' });
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
    
  } catch (err) {
    item.retryCount++;
    item.queuedAt = Date.now(); // Reset for next retry
    
    if (item.retryCount >= RETRY_DELAYS.length) {
      // Give up, remove from queue
      reportQueue.shift();
      stats.failed++;
      Logger.error(`Report failed permanently: ${item.type} - ${err.message}`, { 
        module: 'report_service' 
      });
    } else {
      Logger.warn(`Retry ${item.retryCount} failed for ${item.type}, will retry`, { 
        module: 'report_service' 
      });
    }
  }
}

// ============================================================================
// Scheduler
// ============================================================================

/**
 * Check if it's time for hourly report
 */
function shouldSendHourly() {
  const now = new Date();
  return now.getMinutes() === config.hourlyMinute;
}

/**
 * Check if it's time for daily report
 */
function shouldSendDaily() {
  const now = new Date();
  return now.getHours() === config.dailyHour && now.getMinutes() === 0;
}

/**
 * Scheduler loop
 */
async function schedulerTick() {
  // Check hourly
  if (config.hourlyEnabled && shouldSendHourly()) {
    const report = generateHourlyReport();
    await sendReport(report);
  }
  
  // Check daily
  if (config.dailyEnabled && shouldSendDaily()) {
    const report = generateDailyReport();
    await sendReport(report);
  }
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Configure report service
 */
function configure(options) {
  config = { ...config, ...options };
  Logger.info('Report service configured', { 
    module: 'report_service',
    hourly: config.hourlyEnabled,
    daily: config.dailyEnabled
  });
}

/**
 * Start report service
 */
function start(options = {}) {
  if (isRunning) {
    Logger.warn('Report service already running', { module: 'report_service' });
    return;
  }
  
  if (options) {
    configure(options);
  }
  
  isRunning = true;
  
  // Schedule reports (every minute to check time)
  hourlyInterval = setInterval(schedulerTick, 60000);
  
  // Process queue every 10 seconds
  processQueueInterval = setInterval(processQueue, 10000);
  
  Logger.info('Report service started', { module: 'report_service' });
  
  // Initial report
  schedulerTick().catch(err => {
    Logger.error(`Initial report failed: ${err.message}`, { module: 'report_service' });
  });
}

/**
 * Stop report service
 */
function stop() {
  if (!isRunning) return;
  
  if (hourlyInterval) {
    clearInterval(hourlyInterval);
    hourlyInterval = null;
  }
  
  if (processQueueInterval) {
    clearInterval(processQueueInterval);
    processQueueInterval = null;
  }
  
  isRunning = false;
  Logger.info('Report service stopped', { module: 'report_service' });
}

/**
 * Force send hourly report now
 */
async function sendHourlyNow() {
  const report = generateHourlyReport();
  return sendReport(report);
}

/**
 * Force send daily report now
 */
async function sendDailyNow() {
  const report = generateDailyReport();
  return sendReport(report);
}

/**
 * Get current status
 */
function getStatus() {
  return {
    isRunning,
    queueSize: reportQueue.length,
    stats: { ...stats },
    config: { ...config }
  };
}

/**
 * Clear queue (for testing)
 */
function clearQueue() {
  reportQueue.length = 0;
  Logger.debug('Report queue cleared', { module: 'report_service' });
}

// ============================================================================
// Exports
// ============================================================================

module.exports = {
  configure,
  start,
  stop,
  sendHourlyNow,
  sendDailyNow,
  getStatus,
  clearQueue,
  ReportType,
  // For testing
  generateHourlyReport,
  generateDailyReport,
  formatReportForDiscord,
  queueReport,
  processQueue,
  _reset: () => {
    stop();
    config = {
      discordWebhook: null,
      hourlyEnabled: true,
      dailyEnabled: true,
      hourlyMinute: DEFAULT_HOURLY_MINUTE,
      dailyHour: DEFAULT_DAILY_HOUR
    };
    stats = { sent: 0, queued: 0, failed: 0, deduped: 0 };
    lastSentTimes.clear();
    clearQueue();
  }
};
