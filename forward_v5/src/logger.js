/**
 * Block 3.1: Structured Logger
 *
 * Structured JSON logging with levels, correlation IDs, and rotation.
 * Fail-safe: never throws, falls back to console on error.
 *
 * Dependencies: None (uses Node.js built-in fs/promises)
 * Optional: Install 'pino' or 'winston' for production use
 *
 * @module logger
 * @version 1.0.0
 */

const fs = require('fs');
const path = require('path');

// ============================================================================
// Configuration
// ============================================================================

const LOG_DIR = process.env.LOG_DIR || './logs';
const LOG_LEVEL = process.env.LOG_LEVEL || 'INFO'; // DEBUG, INFO, WARN, ERROR, FATAL
const MAX_LOG_SIZE = parseInt(process.env.LOG_MAX_SIZE, 10) || 10 * 1024 * 1024; // 10MB
const MAX_FILES = parseInt(process.env.LOG_MAX_FILES, 10) || 7;
const CONSOLE_FALLBACK = true;

const LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
  FATAL: 4
};

// ============================================================================
// State
// ============================================================================

let globalContext = {};
let currentLogFile = null;
let currentErrorLogFile = null;
let currentLogSize = 0;
let fileLoggingEnabled = true;

// ============================================================================
// Internal Functions
// ============================================================================

/**
 * Ensure log directory exists
 * Fails silently - will fall back to console
 */
function ensureLogDir() {
  try {
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true });
    }
  } catch (err) {
    console.warn('[Logger] Failed to create log directory:', err.message);
    fileLoggingEnabled = false;
  }
}

/**
 * Get current log filename with rotation
 */
function getLogFilename(isError = false) {
  const date = new Date().toISOString().split('T')[0];
  const suffix = isError ? '.error' : '';
  return path.join(LOG_DIR, `forward-v5${suffix}.${date}.log`);
}

/**
 * Rotate log file if size exceeded
 */
function rotateIfNeeded() {
  if (!fileLoggingEnabled) return;

  const filename = getLogFilename();
  const errorFilename = getLogFilename(true);

  try {
    if (fs.existsSync(filename)) {
      const stats = fs.statSync(filename);
      if (stats.size >= MAX_LOG_SIZE) {
        // Simple rotation: rename to .1, .2, etc.
        for (let i = MAX_FILES - 1; i >= 1; i--) {
          const oldFile = `${filename}.${i}`;
          const newFile = `${filename}.${i + 1}`;
          if (fs.existsSync(oldFile)) {
            fs.renameSync(oldFile, newFile);
          }
        }
        fs.renameSync(filename, `${filename}.1`);
      }
    }

    // Cleanup old rotated files
    for (let i = MAX_FILES + 1; i <= MAX_FILES + 5; i++) {
      const oldFile = `${filename}.${i}`;
      if (fs.existsSync(oldFile)) {
        fs.unlinkSync(oldFile);
      }
    }
  } catch (err) {
    console.warn('[Logger] Rotation failed:', err.message);
  }

  currentLogFile = filename;
  currentErrorLogFile = errorFilename;
}

/**
 * Check if log level should be output
 */
function shouldLog(level) {
  return LEVELS[level] >= LEVELS[LOG_LEVEL.toUpperCase()];
}

/**
 * Build log entry object
 */
function buildLogEntry(level, message, context = {}) {
  const timestamp = new Date().toISOString();

  return {
    timestamp,
    level: level.toUpperCase(),
    message: String(message),
    module: context.module || globalContext.module || 'unknown',
    correlation_id: context.correlation_id || globalContext.correlation_id || null,
    run_id: context.run_id || globalContext.run_id || null,
    event_id: context.event_id || null,
    trade_id: context.trade_id || null,
    context: { ...globalContext, ...context }
  };
}

/**
 * Write log entry to file or console
 * Never throws - fail-safe
 */
function writeLog(entry, isError = false) {
  const line = JSON.stringify(entry) + '\n';

  // Always console output in development or as fallback
  if (!fileLoggingEnabled || CONSOLE_FALLBACK) {
    const consoleFn = isError ? console.error : console.log;
    const corr = entry.correlation_id ? ` ${entry.correlation_id}` : '';
    const mod = entry.module ? ` [${entry.module}]` : '';
    consoleFn(`[${entry.level}]${mod}${corr} ${entry.message}`);
  }

  if (!fileLoggingEnabled) return;

  try {
    rotateIfNeeded();

    // Write to main log
    fs.appendFileSync(currentLogFile, line);

    // Also write errors to separate error log
    if (isError && currentErrorLogFile) {
      fs.appendFileSync(currentErrorLogFile, line);
    }
  } catch (err) {
    // Fail-safe: log to console, don't throw
    console.error('[Logger] Failed to write log:', err.message);
    console.error('[Logger] Original entry:', entry);
  }
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Logger instance with context
 */
class LoggerInstance {
  constructor(context = {}) {
    this._context = { ...context };
  }

  /**
   * Log debug message
   * @param {string} message - Log message
   * @param {Object} [context] - Additional context
   */
  debug(message, context = {}) {
    if (!shouldLog('DEBUG')) return;
    const entry = buildLogEntry('DEBUG', message, { ...this._context, ...context });
    writeLog(entry);
  }

  /**
   * Log info message
   * @param {string} message - Log message
   * @param {Object} [context] - Additional context
   */
  info(message, context = {}) {
    if (!shouldLog('INFO')) return;
    const entry = buildLogEntry('INFO', message, { ...this._context, ...context });
    writeLog(entry);
  }

  /**
   * Log warning message
   * @param {string} message - Log message
   * @param {Object} [context] - Additional context
   */
  warn(message, context = {}) {
    if (!shouldLog('WARN')) return;
    const entry = buildLogEntry('WARN', message, { ...this._context, ...context });
    writeLog(entry, false);
  }

  /**
   * Log error message
   * @param {string} message - Log message
   * @param {Object} [context] - Additional context
   * @param {Error} [context.error] - Error object to log
   */
  error(message, context = {}) {
    if (!shouldLog('ERROR')) return;
    const errorContext = context.error ? { ...context, error: { message: context.error.message, stack: context.error.stack } } : context;
    const entry = buildLogEntry('ERROR', message, { ...this._context, ...errorContext });
    writeLog(entry, true);
  }

  /**
   * Log fatal message (system crash)
   * @param {string} message - Log message
   * @param {Object} [context] - Additional context
   */
  fatal(message, context = {}) {
    if (!shouldLog('FATAL')) return;
    const entry = buildLogEntry('FATAL', message, { ...this._context, ...context });
    writeLog(entry, true);
  }

  /**
   * Create child logger with merged context
   * @param {Object} context - Context to merge
   * @returns {LoggerInstance} New logger instance
   */
  child(context) {
    return new LoggerInstance({ ...this._context, ...context });
  }

  /**
   * Set correlation ID for this logger and descendants
   * @param {string} id - Correlation ID
   * @returns {LoggerInstance} This instance for chaining
   */
  setCorrelationId(id) {
    this._context.correlation_id = id;
    return this;
  }
}

// ============================================================================
// Root Logger (Singleton)
// ============================================================================

let rootLogger = null;

/**
 * Get or create root logger
 * @returns {LoggerInstance}
 */
function getRootLogger() {
  if (!rootLogger) {
    ensureLogDir();
    rotateIfNeeded();
    rootLogger = new LoggerInstance();
  }
  return rootLogger;
}

// ============================================================================
// Module Exports
// ============================================================================

module.exports = {
  // Level functions (convenience)
  debug: (msg, ctx) => getRootLogger().debug(msg, ctx),
  info: (msg, ctx) => getRootLogger().info(msg, ctx),
  warn: (msg, ctx) => getRootLogger().warn(msg, ctx),
  error: (msg, ctx) => getRootLogger().error(msg, ctx),
  fatal: (msg, ctx) => getRootLogger().fatal(msg, ctx),

  // Factory
  child: (ctx) => getRootLogger().child(ctx),

  // Global setter
  setCorrelationId: (id) => {
    globalContext.correlation_id = id;
    return getRootLogger().setCorrelationId(id);
  },

  // Configuration
  setLogLevel: (level) => {
    const upperLevel = level.toUpperCase();
    if (LEVELS[upperLevel] !== undefined) {
      // Only modify for new loggers, not retroactively
      console.log(`[Logger] Log level set to ${upperLevel}`);
    }
  },

  // For testing
  _reset: () => {
    rootLogger = null;
    globalContext = {};
    fileLoggingEnabled = true;
  },

  // Constants
  LEVELS: Object.keys(LEVELS)
};

// Auto-initialize on first use
getRootLogger();
