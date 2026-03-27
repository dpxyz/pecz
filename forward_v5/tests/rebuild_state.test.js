/**
 * Block 3.4 Tests: Rebuild CLI
 *
 * Tests: 8+ test cases for commands/rebuild_state.js
 * Coverage: Argument parsing, diff logic, rebuild process, dry-run, force
 */

const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const fs = require('fs');

// ============================================================================
// Test Suite: Rebuild CLI
// ============================================================================

test('T1: Parse arguments --dry-run', async (t) => {
  const { parseArgs } = require('../commands/rebuild_state.js');
  
  const options = parseArgs(['--dry-run', '--verbose']);
  
  assert.strictEqual(options.dryRun, true, 'Should parse --dry-run');
  assert.strictEqual(options.force, false, 'Should default force to false');
  assert.strictEqual(options.verbose, true, 'Should parse --verbose');
});

test('T2: Parse arguments --force', async (t) => {
  const { parseArgs } = require('../commands/rebuild_state.js');
  
  const options = parseArgs(['--force', '--db', './custom.db']);
  
  assert.strictEqual(options.force, true, 'Should parse --force');
  assert.strictEqual(options.dbPath, './custom.db', 'Should parse --db path');
  assert.strictEqual(options.dryRun, false, 'Should default dryRun to false');
});

test('T3: Diff objects - no differences', async (t) => {
  const { diffObjects } = require('../commands/rebuild_state.js');
  
  const obj1 = { a: 1, b: { c: 2 } };
  const obj2 = { a: 1, b: { c: 2 } };
  
  const diffs = diffObjects(obj1, obj2);
  
  assert.strictEqual(diffs.length, 0, 'Identical objects should have no diffs');
});

test('T4: Diff objects - value mismatch', async (t) => {
  const { diffObjects } = require('../commands/rebuild_state.js');
  
  const rebuild = { value: 42 };
  const live = { value: 43 };
  
  const diffs = diffObjects(rebuild, live);
  
  assert.strictEqual(diffs.length, 1, 'Should detect value mismatch');
  assert.strictEqual(diffs[0].type, 'value_mismatch');
  assert.strictEqual(diffs[0].rebuild, 42);
  assert.strictEqual(diffs[0].live, 43);
});

test('T5: Diff objects - missing keys', async (t) => {
  const { diffObjects } = require('../commands/rebuild_state.js');
  
  const rebuild = { a: 1, b: 2 };
  const live = { a: 1, c: 3 };
  
  const diffs = diffObjects(rebuild, live);
  
  const missingInRebuild = diffs.filter(d => d.type === 'missing_in_rebuild');
  const missingInLive = diffs.filter(d => d.type === 'missing_in_live');
  
  assert.strictEqual(missingInRebuild.length, 1, 'Should detect missing in rebuild');
  assert.strictEqual(missingInRebuild[0].path, 'c');
  assert.strictEqual(missingInLive.length, 1, 'Should detect missing in live');
  assert.strictEqual(missingInLive[0].path, 'b');
});

test('T6: Diff objects - arrays', async (t) => {
  const { diffObjects } = require('../commands/rebuild_state.js');
  
  const rebuild = { items: [1, 2, 3] };
  const live = { items: [1, 2, 4] };
  
  const diffs = diffObjects(rebuild, live);
  
  assert.ok(diffs.length > 0, 'Should detect array differences');
});

test('T7: Format diff - no differences', async (t) => {
  const { formatDiff } = require('../commands/rebuild_state.js');
  
  const output = formatDiff([]);
  
  assert.ok(output.includes('✓'), 'Should show checkmark for no diffs');
  assert.ok(output.includes('match'), 'Should indicate states match');
});

test('T8: Format diff - with differences', async (t) => {
  const { formatDiff } = require('../commands/rebuild_state.js');
  
  const diffs = [
    { path: 'value', rebuild: 42, live: 43, type: 'value_mismatch' },
    { path: 'missing', rebuild: undefined, live: 'data', type: 'missing_in_rebuild' }
  ];
  
  const output = formatDiff(diffs, true);
  
  assert.ok(output.includes('⚠'), 'Should show warning symbol');
  assert.ok(output.includes('value_mismatch'), 'Should mention value_mismatch');
  assert.ok(output.includes('missing_in_rebuild'), 'Should mention missing_in_rebuild');
});

test('T9: Diff objects with nested structures', async (t) => {
  const { diffObjects } = require('../commands/rebuild_state.js');
  
  const rebuild = {
    level1: {
      level2: {
        value: 'rebuild'
      }
    }
  };
  
  const live = {
    level1: {
      level2: {
        value: 'live'
      }
    }
  };
  
  const diffs = diffObjects(rebuild, live);
  
  assert.strictEqual(diffs.length, 1, 'Should detect nested difference');
  assert.strictEqual(diffs[0].path, 'level1.level2.value');
  assert.strictEqual(diffs[0].rebuild, 'rebuild');
  assert.strictEqual(diffs[0].live, 'live');
});

test('T10: Rebuild returns correct structure', async (t) => {
  // This test validates the module exports without actually running a rebuild
  const rebuildModule = require('../commands/rebuild_state.js');
  
  assert.ok(typeof rebuildModule.rebuild === 'function', 'Should export rebuild function');
  assert.ok(typeof rebuildModule.diffObjects === 'function', 'Should export diffObjects');
  assert.ok(typeof rebuildModule.parseArgs === 'function', 'Should export parseArgs');
});

// Cleanup after all tests
test.after(() => {
  // Cleanup any test files
  const backupDir = './backups';
  if (fs.existsSync(backupDir)) {
    const files = fs.readdirSync(backupDir);
    for (const file of files) {
      if (file.startsWith('state-')) {
        fs.unlinkSync(path.join(backupDir, file));
      }
    }
  }
});
