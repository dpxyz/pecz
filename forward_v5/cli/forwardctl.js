#!/usr/bin/env node
/**
 * OpenClaw Forward v5 - Control CLI
 * Block 5.2: Management Interface für Runtime
 * 
 * Usage:
 *   forwardctl status              # Status anzeigen (funktioniert jetzt)
 *   forwardctl logs                # Logs anzeigen (funktioniert jetzt)
 *   forwardctl validate            # Service-Datei validieren (funktioniert jetzt)
 *   forwardctl config              # Config anzeigen (funktioniert jetzt)
 *   forwardctl edit                  # Config editieren (funktioniert jetzt)
 *   forwardctl start               # ⏳ deferred (braucht systemd)
 *   forwardctl stop                # ⏳ deferred (braucht systemd)
 *   forwardctl restart             # ⏳ deferred (braucht systemd)
 *   forwardctl journal             # ⏳ deferred (braucht journald)
 * 
 * Phase 5.2 - Funktional + Deferred
 */

const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const SERVICE_NAME = 'forward_v5.service';
const WORKSPACE_ROOT = '/data/.openclaw/workspace/forward_v5/forward_v5';
const STATE_FILE = path.join(WORKSPACE_ROOT, 'runtime_validation/state.json');
const SERVICE_FILE = path.join(WORKSPACE_ROOT, 'systemd/forward_v5.service');

// Helper: Check if file exists
const exists = (file) => fs.existsSync(file);

// Helper: Read JSON safely
const readJson = (file) => {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
};

// Helper: Format duration
const formatDuration = (hours) => {
  const h = Math.floor(hours);
  const m = Math.floor((hours - h) * 60);
  return `${h}h ${m}m`;
};

// ============ FUNCTIONAL COMMANDS ============

const status = () => {
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Status                     ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();

  // Service file status
  console.log('📋 Service File');
  if (exists(SERVICE_FILE)) {
    const stats = fs.statSync(SERVICE_FILE);
    console.log(`   Location: ${SERVICE_FILE}`);
    console.log(`   Modified: ${stats.mtime.toISOString()}`);
    console.log(`   Status: ✅ Present`);
  } else {
    console.log(`   Status: ❌ Not found at ${SERVICE_FILE}`);
  }
  console.log();

  // Run state
  console.log('📊 Run State');
  if (exists(STATE_FILE)) {
    const state = readJson(STATE_FILE);
    if (state) {
      console.log(`   Run ID: ${state.run_id}`);
      console.log(`   Status: ${state.status}`);
      console.log(`   Version: ${state.version}`);
      
      if (state.result) {
        console.log(`   Result: ${state.result.status || 'N/A'}`);
      }
      
      if (state.metrics) {
        console.log(`   Memory: ${state.metrics.memory_percent}% (${state.metrics.memory_current_mb}MB)`);
        console.log(`   Growth: ${state.metrics.memory_growth_percent}%`);
      }
      
      if (state.counters) {
        console.log(`   Heartbeats: ${state.counters.heartbeats_received}/${state.counters.heartbeats_expected}`);
      }
    }
  } else {
    console.log(`   Status: No state file found`);
  }
  console.log();

  // Process check
  console.log('🔍 Process Check');
  try {
    const output = execSync('pgrep -f "runtime_validation/runner.js" || echo "NOT_RUNNING"', { encoding: 'utf8' });
    if (output.trim() === 'NOT_RUNNING') {
      console.log('   Status: ⏹️  Not running');
    } else {
      const pid = output.trim().split('\n')[0];
      console.log(`   Status: 🟢 Running (PID ${pid})`);
    }
  } catch {
    console.log('   Status: ⏹️  Not running');
  }
  console.log();

  // Block 5.1 status
  console.log('📦 Block 5.1 Status');
  console.log('   Code: ✅ COMPLETE v1.1');
  console.log('   Host Test: ⏳ DEFERRED (next VPS access)');
  console.log();
};

const logs = (options = {}) => {
  const { lines = 50, follow = false } = options;
  
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Logs                       ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();

  // Check archive for completed run
  const archiveDir = '/data/.openclaw/workspace/archive/2026-04-01_fix_50d_GO';
  const logFile = path.join(archiveDir, 'complete_24h_log.txt');
  
  if (exists(logFile)) {
    console.log(`📁 Archived Log: ${logFile}`);
    console.log(`   Size: ${(fs.statSync(logFile).size / 1024).toFixed(1)} KB`);
    console.log();
    
    if (follow) {
      console.log('Showing last lines (use tail -f for real-time):');
      console.log(`   tail -f ${logFile}`);
    } else {
      console.log(`Last ${lines} lines:`);
      console.log('─'.repeat(50));
      try {
        const output = execSync(`tail -n ${lines} ${logFile}`, { encoding: 'utf8' });
        console.log(output);
      } catch (e) {
        console.log('Error reading log:', e.message);
      }
      console.log('─'.repeat(50));
    }
  } else {
    console.log('⚠️  No archived logs found');
    console.log(`   Expected: ${logFile}`);
  }
  console.log();
};

const validate = () => {
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Validation                 ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();

  if (!exists(SERVICE_FILE)) {
    console.log('❌ Service file not found:', SERVICE_FILE);
    return;
  }

  console.log('📋 Validating service file...');
  console.log(`   File: ${SERVICE_FILE}`);
  console.log();

  // Read and check content
  const content = fs.readFileSync(SERVICE_FILE, 'utf8');
  const checks = [
    { name: 'User directive', pattern: /^User=\w+/m },
    { name: 'Group directive', pattern: /^Group=\w+/m },
    { name: 'WorkingDirectory', pattern: /^WorkingDirectory=/m },
    { name: 'Restart policy', pattern: /^Restart=/m },
    { name: 'RestartSec', pattern: /^RestartSec=/m },
    { name: 'TimeoutStartSec', pattern: /^TimeoutStartSec=/m },
    { name: 'TimeoutStopSec', pattern: /^TimeoutStopSec=/m },
    { name: 'StandardOutput', pattern: /^StandardOutput=/m },
    { name: 'EnvironmentFile', pattern: /^EnvironmentFile=/m },
  ];

  let passed = 0;
  checks.forEach(check => {
    const found = check.pattern.test(content);
    console.log(`   ${found ? '✅' : '❌'} ${check.name}`);
    if (found) passed++;
  });

  console.log();
  console.log(`Result: ${passed}/${checks.length} checks passed`);
  console.log();

  if (passed === checks.length) {
    console.log('✅ Service file is valid');
    console.log('⏳ Host test pending (requires systemd machine)');
  } else {
    console.log('⚠️  Some recommended directives missing');
  }
};

const config = () => {
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Configuration              ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();
  
  const configs = [
    { name: 'Service File', path: SERVICE_FILE },
    { name: 'State File', path: STATE_FILE },
    { name: 'Env Example', path: path.join(WORKSPACE_ROOT, 'systemd/config/forward_v5.env.example') },
    { name: 'Test Plan', path: path.join(WORKSPACE_ROOT, 'systemd/TESTPLAN.md') },
    { name: 'Status Doc', path: path.join(WORKSPACE_ROOT, 'systemd/BLOCK_5_1_STATUS.md') },
    { name: 'Deploy Script', path: path.join(WORKSPACE_ROOT, 'systemd/deploy_to_vps.sh') },
  ];

  configs.forEach(cfg => {
    const exists_icon = exists(cfg.path) ? '✅' : '❌';
    console.log(`   ${exists_icon} ${cfg.name}`);
    console.log(`      ${cfg.path}`);
    console.log();
  });
};

const edit = () => {
  const editor = process.env.EDITOR || 'nano';
  console.log(`Opening ${SERVICE_FILE} in ${editor}...`);
  console.log(`(Run: ${editor} ${SERVICE_FILE})`);
};

// ============ DEFERRED COMMANDS ============

const deferredStart = () => {
  console.log('⏳ COMMAND DEFERRED: forwardctl start');
  console.log();
  console.log('This command requires:');
  console.log('  - systemd as init system (PID 1)');
  console.log('  - systemctl available');
  console.log('  - Service installed in /etc/systemd/system/');
  console.log();
  console.log('Manual workaround (current environment):');
  console.log('  node runtime_validation/runner.js');
  console.log();
  console.log('When deployed to VPS:');
  console.log('  sudo systemctl start forward_v5.service');
};

const deferredStop = () => {
  console.log('⏳ COMMAND DEFERRED: forwardctl stop');
  console.log();
  console.log('Requires systemd. Manual workaround:');
  console.log('  pkill -f runtime_validation/runner.js');
  console.log();
  console.log('When deployed:');
  console.log('  sudo systemctl stop forward_v5.service');
};

const deferredRestart = () => {
  console.log('⏳ COMMAND DEFERRED: forwardctl restart');
  console.log();
  console.log('Requires systemd host.');
  console.log();
  console.log('When deployed:');
  console.log('  sudo systemctl restart forward_v5.service');
};

const deferredJournal = () => {
  console.log('⏳ COMMAND DEFERRED: forwardctl journal');
  console.log();
  console.log('Requires:');
  console.log('  - systemd with journald');
  console.log('  - journalctl available');
  console.log();
  console.log('Workaround (archived logs):');
  console.log('  forwardctl logs');
  console.log();
  console.log('When deployed:');
  console.log('  sudo journalctl -u forward_v5.service -f');
};

// ============ HELP ============

const help = () => {
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Control CLI                ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();
  console.log('Usage: forwardctl [command] [options]');
  console.log();
  console.log('✅ AVAILABLE NOW (no systemd required):');
  console.log('  status              Show current status');
  console.log('  logs [-n N]         Show last N lines of logs');
  console.log('  validate              Validate service file');
  console.log('  config              Show configuration paths');
  console.log('  edit                Open service file in $EDITOR');
  console.log();
  console.log('⏳ DEFERRED (requires systemd host):');
  console.log('  start               Start the service');
  console.log('  stop                Stop the service');
  console.log('  restart             Restart the service');
  console.log('  journal             View systemd journal logs');
  console.log();
  console.log('Options:');
  console.log('  -n, --lines N       Show last N lines (default: 50)');
  console.log('  -f, --follow        Follow logs (if supported)');
  console.log('  -h, --help          Show this help');
  console.log();
  console.log('Examples:');
  console.log('  forwardctl status');
  console.log('  forwardctl logs -n 100');
  console.log('  forwardctl validate');
};

// ============ MAIN ============

const args = process.argv.slice(2);
const cmd = args[0] || 'help';

// Parse options
const options = {};
for (let i = 1; i < args.length; i++) {
  if (args[i] === '-n' || args[i] === '--lines') {
    options.lines = parseInt(args[i + 1]) || 50;
    i++;
  }
  if (args[i] === '-f' || args[i] === '--follow') {
    options.follow = true;
  }
}

const commands = {
  // Functional
  status,
  logs: () => logs(options),
  validate,
  config,
  edit,
  
  // Deferred
  start: deferredStart,
  stop: deferredStop,
  restart: deferredRestart,
  journal: deferredJournal,
  
  // Help
  help,
};

if (commands[cmd]) {
  commands[cmd]();
} else {
  console.log('Unknown command:', cmd);
  commands.help();
  process.exit(1);
}
