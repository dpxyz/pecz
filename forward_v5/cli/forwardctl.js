#!/usr/bin/env node
/**
 * OpenClaw Forward v5 - Control CLI
 * Block 5.2: Management Interface für Runtime
 * 
 * Commands:
 *   forwardctl status     -> Service status anzeigen
 *   forwardctl start      -> Service starten (systemctl start)
 *   forwardctl stop       -> Service stoppen (systemctl stop)
 *   forwardctl restart    -> Service neustarten
 *   forwardctl logs       -> Logs anzeigen (journalctl)
 *   forwardctl config     -> Config bearbeiten
 * 
 * Phase 5.2 - Work in Progress
 */

const { execSync } = require('child_process');
const path = require('path');

const SERVICE_NAME = 'forward_v5.service';
const WORKSPACE_ROOT = '/data/.openclaw/workspace/forward_v5/forward_v5';

// Command handlers
const commands = {
  status: () => {
    console.log('=== Forward v5 Status ===');
    console.log('Service:', SERVICE_NAME);
    console.log('Status: See systemctl status (requires systemd)');
    console.log('');
    console.log('Note: Full status requires systemd environment');
  },

  start: () => {
    console.log('Starting forward_v5 service...');
    console.log('Command: sudo systemctl start', SERVICE_NAME);
    console.log('');
    console.log('Note: Requires systemd. For now, run manually:');
    console.log('  node runtime_validation/runner.js');
  },

  stop: () => {
    console.log('Stopping forward_v5 service...');
    console.log('Command: sudo systemctl stop', SERVICE_NAME);
    console.log('');
    console.log('Note: Requires systemd');
  },

  restart: () => {
    console.log('Restarting forward_v5 service...');
    console.log('Command: sudo systemctl restart', SERVICE_NAME);
    console.log('');
    console.log('Note: Requires systemd');
  },

  logs: () => {
    console.log('Viewing logs...');
    console.log('Command: sudo journalctl -u', SERVICE_NAME, '-f');
    console.log('');
    console.log('Alternative (current log):');
    console.log('  tail -f /tmp/fix_50d_2h_test.log');
  },

  config: () => {
    console.log('Configuration:');
    console.log('  Service file:', path.join(WORKSPACE_ROOT, 'systemd/forward_v5.service'));
    console.log('  Env example:', path.join(WORKSPACE_ROOT, 'systemd/config/forward_v5.env.example'));
    console.log('  Status doc:', path.join(WORKSPACE_ROOT, 'systemd/BLOCK_5_1_STATUS.md'));
  },

  help: () => {
    console.log('OpenClaw Forward v5 Control CLI');
    console.log('');
    console.log('Usage: forwardctl [command]');
    console.log('');
    console.log('Commands:');
    console.log('  status     Show service status');
    console.log('  start      Start the service');
    console.log('  stop       Stop the service');
    console.log('  restart    Restart the service');
    console.log('  logs       View logs');
    console.log('  config     Show configuration paths');
    console.log('  help       Show this help');
    console.log('');
    console.log('Note: Full functionality requires systemd on target host');
  }
};

// Main
const cmd = process.argv[2] || 'help';

if (commands[cmd]) {
  commands[cmd]();
} else {
  console.log('Unknown command:', cmd);
  commands.help();
  process.exit(1);
}
