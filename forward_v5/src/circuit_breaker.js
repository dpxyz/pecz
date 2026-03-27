/**
 * Circuit Breaker MVP
 * 
 * Zustände: CLOSED → OPEN → HALF_OPEN → CLOSED
 * 
 * Regeln:
 * - Nur SAFETY-Fehler öffnen den Breaker
 * - OBSERVABILITY-Fehler tun NICHTS
 * - OPEN = Trading blockiert
 * - Resume nur manuell via attemptReset()/confirmReset()
 */

const Logger = require('./logger.js');
const Health = require('./health.js');

// Zustände als Konstanten
const States = {
  CLOSED: 'CLOSED',
  OPEN: 'OPEN', 
  HALF_OPEN: 'HALF_OPEN'
};

// Privater Zustand (nicht direkt exportiert)
let state = States.CLOSED;
let failureCount = 0;
let lastFailureTime = null;
let safetyFailures = [];

// Event-Callbacks (optional)
let onStateChange = null;

/**
 * Circuit Breaker initialisieren
 * @param {Object} options
 * @param {Function} options.onStateChange - Callback bei Zustandsänderung
 */
function configure(options = {}) {
  if (options.onStateChange) {
    onStateChange = options.onStateChange;
  }
  Logger.info('CircuitBreaker configured', { module: 'circuit_breaker' });
}

/**
 * SAFETY-Fehler aufzeichnen → kann OPEN auslösen
 * @param {string} checkName - Name des fehlgeschlagenen Checks
 * @param {Object} details - Fehler-Details
 */
function recordSafetyFailure(checkName, details = {}) {
  const failure = { checkName, details, time: Date.now() };
  safetyFailures.push(failure);
  failureCount++;
  lastFailureTime = Date.now();

  Logger.error('SAFETY violation recorded', { 
    module: 'circuit_breaker',
    check: checkName,
    details
  });

  // Nur wenn CLOSED → OPEN
  if (state === States.CLOSED) {
    _open();
  }
}

/**
 * OBSERVABILITY-Fehler aufzeichnen → TUT NICHTS am Breaker
 * @param {string} checkName - Name des fehlgeschlagenen Checks
 */
function recordObservabilityFailure(checkName) {
  // ABSOLUTE REGEL: NIE den Breaker öffnen
  Logger.warn(`OBSERVABILITY failure logged only: ${checkName}`, { 
    module: 'circuit_breaker' 
  });
  // Keine Zustandsänderung!
}

/**
 * Breaker auf OPEN setzen (privat)
 */
function _open() {
  const oldState = state;
  state = States.OPEN;
  
  Logger.fatal('Circuit Breaker OPEN - Trading HALTED', { 
    module: 'circuit_breaker',
    previousState: oldState
  });

  _emitEvent('CIRCUIT_BREAKER_OPENED', { 
    failureCount, 
    safetyFailures 
  });
}

/**
 * Manuelles Reset: OPEN → HALF_OPEN
 * @returns {boolean} true wenn Transition erfolgreich
 */
function attemptReset() {
  if (state !== States.OPEN) {
    Logger.warn('attemptReset() ignored: not in OPEN state', { 
      module: 'circuit_breaker',
      currentState: state
    });
    return false;
  }

  state = States.HALF_OPEN;
  
  Logger.info('Circuit Breaker HALF_OPEN - Recovery validation started', { 
    module: 'circuit_breaker' 
  });

  _emitEvent('CIRCUIT_BREAKER_HALF_OPEN', {});
  return true;
}

/**
 * Reset bestätigen: HALF_OPEN → CLOSED (nur wenn Health OK)
 * @returns {boolean} true wenn zurück in CLOSED
 */
function confirmReset() {
  if (state !== States.HALF_OPEN) {
    Logger.warn('confirmReset() ignored: not in HALF_OPEN state', { 
      module: 'circuit_breaker',
      currentState: state
    });
    return false;
  }

  // Prüfe alle SAFETY-Checks
  const healthStatus = Health.getStatus ? Health.getStatus() : null;
  const safetyChecks = healthStatus?.safety || [];
  const allSafetyOk = safetyChecks.every(c => c.status === 'OK');

  if (!allSafetyOk) {
    Logger.warn('confirmReset() blocked: SAFETY checks not all OK', { 
      module: 'circuit_breaker',
      safetyChecks
    });
    return false;
  }

  // Reset state
  const oldState = state;
  state = States.CLOSED;
  failureCount = 0;
  safetyFailures = [];

  Logger.info('Circuit Breaker CLOSED - Trading resumed', { 
    module: 'circuit_breaker',
    previousState: oldState
  });

  _emitEvent('CIRCUIT_BREAKER_CLOSED', {});
  return true;
}

/**
 * Ist Trading erlaubt?
 * @returns {boolean}
 */
function isTradingAllowed() {
  return state === States.CLOSED;
}

/**
 * Aktuellen Status abfragen
 * @returns {Object}
 */
function getStatus() {
  return {
    state,
    isTradingAllowed: state === States.CLOSED,
    failureCount,
    lastFailureTime,
    safetyFailureCount: safetyFailures.length
  };
}

/**
 * Event emittieren (privat)
 */
function _emitEvent(eventType, data) {
  // Globaler Event-Store oder Callback
  if (onStateChange) {
    try {
      onStateChange(eventType, { ...data, newState: state });
    } catch (e) {
      Logger.error('State change callback failed', { 
        module: 'circuit_breaker',
        error: e.message
      });
    }
  }
}

/**
 * Intern zurücksetzen (nur für Tests)
 */
function _reset() {
  state = States.CLOSED;
  failureCount = 0;
  lastFailureTime = null;
  safetyFailures = [];
}

module.exports = {
  // API
  configure,
  recordSafetyFailure,
  recordObservabilityFailure,
  attemptReset,
  confirmReset,
  isTradingAllowed,
  getStatus,
  
  // Intern für Tests
  _reset,
  
  // Konstanten
  States
};
