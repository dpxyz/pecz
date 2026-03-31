const path = require('path');

// Load services (runner is in runtime_validation/, so paths are ../)
const heartbeat = require('../src/heartbeat_service');
const healthChecker = require('../src/health_checker');

console.log('');
console.log('===================================================================');
console.log('Runtime Validation Services Starting');
console.log('===================================================================');
console.log('');

// P0 Fix: Pre-flight validation
console.log('Pre-flight checks...');

// Check EVENT_STORE_PATH
if (!process.env.EVENT_STORE_PATH) {
  console.error('CRITICAL: EVENT_STORE_PATH environment variable not set');
  console.error('Export with: export EVENT_STORE_PATH=/data/.openclaw/workspace/forward_v5/forward_v5/runtime/event_store.db');
  process.exit(1);
}
console.log(`✓ EVENT_STORE_PATH: ${process.env.EVENT_STORE_PATH}`);

// Start heartbeat service first
heartbeat.start();

// Connect health checker to heartbeat
healthChecker.setHeartbeatService(heartbeat);

// Start health checker (will validate EVENT_STORE_PATH)
try {
  healthChecker.start();
} catch (err) {
  console.error('Failed to start health checker:', err.message);
  process.exit(1);
}

console.log('');
console.log('Services started successfully');
console.log('Press Ctrl+C to stop gracefully');
console.log('');

// Keep process alive
setInterval(() => {}, 1000);

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down gracefully...');
  heartbeat.stop();
  healthChecker.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  heartbeat.stop();
  healthChecker.stop();
  process.exit(0);
});
