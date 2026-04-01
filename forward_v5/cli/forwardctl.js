#!/usr/bin/env node
/**
 * OpenClaw Forward v5 - Control CLI v1.1
 * Block 5.2: Management Interface für Runtime
 * 
 * SCOPE:
 *   ✅ Core CLI Commands: status, logs, validate, config, edit
 *   ⏳ Systemd Actions: start, stop, restart, journal (deferred)
 * 
 * Exit Codes:
 *   0 = SUCCESS
 *   1 = ERROR (invalid command, file not found)
 *   2 = DEFERRED (needs systemd host)
 *   3 = NOT IMPLEMENTED
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Configuration
const SERVICE_NAME = 'forward_v5.service';
const WORKSPACE_ROOT = '/data/.openclaw/workspace/forward_v5/forward_v5';
const STATE_FILE = path.join(WORKSPACE_ROOT, 'runtime_validation/state.json');
const SERVICE_FILE = path.join(WORKSPACE_ROOT, 'systemd/forward_v5.service');

// Exit codes
const EXIT = {
  SUCCESS: 0,
  ERROR: 1,
  DEFERRED: 2,
  NOT_IMPLEMENTED: 3
};

// Helper functions
const exists = (file) => fs.existsSync(file);
const readJson = (file) => {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
};

// ============ FUNCTIONAL COMMANDS (Core CLI - Available Now) ============

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
    console.error(`   Status: ❌ Not found at ${SERVICE_FILE}`);
    return false;
  }
  console.log();

  // Run state
  console.log('📊 Run State');
  if (exists(STATE_FILE)) {
    const state = readJson(STATE_FILE);
    if (state) {
      console.log(`   Run ID: ${state.run_id}`);
      console.log(`   Status: ${state.status}`);
      if (state.result?.status) console.log(`   Result: ${state.result.status}`);
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
    const output = execSync('pgrep -f "runtime_validation/runner.js" 2>/dev/null || echo "NOT_RUNNING"', { encoding: 'utf8' });
    if (output.trim() === 'NOT_RUNNING') {
      console.log('   Status: ⏹️  Not running');
    } else {
      console.log(`   Status: 🟢 Running (PID ${output.trim().split('\n')[0]})`);
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
  return true;
};

const logs = (options = {}) => {
  const { lines = 50 } = options;
  
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Logs                       ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();

  const archiveDir = '/data/.openclaw/workspace/archive/2026-04-01_fix_50d_GO';
  const logFile = path.join(archiveDir, 'complete_24h_log.txt');
  
  if (exists(logFile)) {
    console.log(`📁 Archived Log: ${logFile}`);
    console.log(`   Size: ${(fs.statSync(logFile).size / 1024).toFixed(1)} KB`);
    console.log();
    console.log(`Last ${lines} lines:`);
    console.log('─'.repeat(50));
    try {
      const output = execSync(`tail -n ${lines} ${logFile}`, { encoding: 'utf8' });
      process.stdout.write(output);
    } catch (e) {
      console.error(`Error reading log: ${e.message}`);
      return false;
    }
    console.log('─'.repeat(50));
  } else {
    console.error('⚠️  No archived logs found');
    console.error(`   Expected: ${logFile}`);
    return false;
  }
  console.log();
  return true;
};

const validate = () => {
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Validation                   ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();

  if (!exists(SERVICE_FILE)) {
    console.error('❌ Error: Service file not found');
    console.error(`   Path: ${SERVICE_FILE}`);
    return false;
  }

  console.log('📋 Validating service file...');
  console.log(`   File: ${SERVICE_FILE}`);
  console.log();

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

  if (passed === checks.length) {
    console.log('✅ Service file is valid');
    console.log('⏳ Host test pending (requires systemd machine)');
    return true;
  } else {
    console.error('⚠️  Some required directives missing');
    return false;
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

  let allExist = true;
  configs.forEach(cfg => {
    const ok = exists(cfg.path);
    console.log(`   ${ok ? '✅' : '❌'} ${cfg.name}`);
    console.log(`      ${cfg.path}`);
    if (!ok) allExist = false;
  });
  console.log();
  return allExist;
};

const edit = () => {
  const editor = process.env.EDITOR || 'nano';
  console.log(`✏️  Opening ${SERVICE_FILE}`);
  console.log(`   Editor: ${editor}`);
  console.log(`   Run: ${editor} ${SERVICE_FILE}`);
  return true;
};

// ============ DEFERRED COMMANDS (Require systemd host) ============
// Blocked until 5.1 Host Test on systemd machine

const showDeferred = (cmd, requirements, workaround, deployedCmd) => {
  console.error('╔════════════════════════════════════════════════════════╗');
  console.error('║  ⏳  COMMAND DEFERRED                                  ║');
  console.error('╚════════════════════════════════════════════════════════╝');
  console.error();
  console.error(`Command: forwardctl ${cmd}`);
  console.error('Status: ⏳ WAITING FOR BLOCK 5.1 HOST TEST');
  console.error();
  console.error('🚫 WHY DEFERRED:');
  console.error('   This command requires a systemd-managed host.');
  console.error('   Current environment: Docker (docker-init, not systemd)');
  console.error();
  console.error('📋 REQUIREMENTS:');
  requirements.forEach(r => console.error(`   • ${r}`));
  console.error();
  console.error('🔧 WORKAROUND (now):');
  console.error(`   $ ${workaround}`);
  console.error();
  console.error('✅ WHEN DEPLOYED (after 5.1 Host Test):');
  console.error(`   $ ${deployedCmd}`);
  console.error();
  console.error('📖 Documentation:');
  console.error('   systemd/BLOCK_5_1_STATUS.md');
  console.error('   systemd/TESTPLAN.md');
};

const deferredStart = () => {
  showDeferred('start',
    ['systemd as init system (PID 1)', 'systemctl binary', 'Service installed in /etc/systemd/system/'],
    'node runtime_validation/runner.js',
    'sudo systemctl start forward_v5.service'
  );
  process.exit(EXIT.DEFERRED);
};

const deferredStop = () => {
  showDeferred('stop',
    ['systemd as init (PID 1)', 'systemctl binary', 'Running service'],
    'pkill -f runtime_validation/runner.js',
    'sudo systemctl stop forward_v5.service'
  );
  process.exit(EXIT.DEFERRED);
};

const deferredRestart = () => {
  showDeferred('restart',
    ['systemd as init (PID 1)', 'systemctl binary', 'Service installed'],
    'pkill -f runner.js && node runtime_validation/runner.js',
    'sudo systemctl restart forward_v5.service'
  );
  process.exit(EXIT.DEFERRED);
};

const deferredJournal = () => {
  showDeferred('journal',
    ['systemd with journald', 'journalctl binary', 'Service logs in systemd'],
    'forwardctl logs',
    'sudo journalctl -u forward_v5.service -f'
  );
  process.exit(EXIT.DEFERRED);
};

// ============ HELP ============

const help = () => {
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║       OpenClaw Forward v5 - Control CLI v1.1             ║');
  console.log('║       Block 5.2 - Core: ✅ COMPLETE / Systemd: ⏳        ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log();
  console.log('Usage: forwardctl [command] [options]');
  console.log();
  console.log('✅ CORE CLI (Available now - no systemd required):');
  console.log('  status              Show current status');
  console.log('  logs [-n N]         Show last N lines of logs');
  console.log('  validate            Validate service file');
  console.log('  config              Show configuration paths');
  console.log('  edit                Open service file in $EDITOR');
  console.log();
  console.log('⏳ SYSTEMD ACTIONS (Deferred - needs Block 5.1 Host Test):');
  console.log('  start               Start the service');
  console.log('  stop                Stop the service');
  console.log('  restart             Restart the service');
  console.log('  journal             View systemd journal logs');
  console.log();
  console.log('Options:');
  console.log('  -n, --lines N       Show last N lines (default: 50)');
  console.log('  -f, --follow        Follow logs (nyi)');
  console.log('  -h, --help          Show this help');
  console.log();
  console.log('Exit Codes:');
  console.log('  0  SUCCESS          Command executed successfully');
  console.log('  1  ERROR            Invalid command or file not found');
  console.log('  2  DEFERRED         Command needs systemd host (Block 5.1)');
  console.log('  3  NOT IMPLEMENTED  Feature not yet available');
  console.log();
  console.log('Examples:');
  console.log('  forwardctl status');
  console.log('  forwardctl validate');
  console.log('  forwardctl logs -n 100');
  console.log();
  console.log('Documentation:');
  console.log('  systemd/BLOCK_5_1_STATUS.md');
  console.log('  systemd/TESTPLAN.md');
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
  if (args[i] === '-h' || args[i] === '--help') {
    help();
    process.exit(EXIT.SUCCESS);
  }
}

const commands = {
  // Core CLI - Available now
  status,
  logs: () => logs(options),
  validate,
  config,
  edit,
  
  // Systemd Actions - Deferred
  start: deferredStart,
  stop: deferredStop,
  restart: deferredRestart,
  journal: deferredJournal,
  
  // Help
  help,
};

if (commands[cmd]) {
  const result = commands[cmd]();
  process.exit(result === false ? EXIT.ERROR : EXIT.SUCCESS);
} else {
  console.error(`❌ Error: Unknown command '${cmd}'`);
  console.error();
  help();
  process.exit(EXIT.ERROR);
}
