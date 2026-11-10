#!/usr/bin/env node
/*
 * inspect-desktop-leveldb.js
 *
 * Inspect a Chromium LocalStorage LevelDB used by the Hermes Desktop app
 * (~/Library/Application Support/Hermes/Local Storage/leveldb/).
 *
 * Usage:
 *   node inspect-desktop-leveldb.js <LEVELDB_PATH> [--keys PATTERN] [--raw]
 *
 * Prints all keys (optionally filtered), with values shown as JSON if parseable
 * or as utf-8 / hex if not. The Chromium LocalStorage key prefix "_file://\x00\x01"
 * is decoded visually so you can read the actual key name.
 *
 * Requires classic-level (npm install classic-level).
 */

const { ClassicLevel } = require('classic-level');
const path = require('path');

function parseArgs() {
  const args = process.argv.slice(2);
  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    console.error('Usage: node inspect-desktop-leveldb.js <LEVELDB_PATH> [--keys PATTERN] [--raw]');
    process.exit(args.length === 0 ? 1 : 0);
  }
  const opts = { path: args[0], keysPattern: null, raw: false };
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--keys') opts.keysPattern = new RegExp(args[++i]);
    else if (args[i] === '--raw') opts.raw = true;
  }
  return opts;
}

function decodeKey(buf) {
  // Chromium LocalStorage key format: "<origin>\x00\x01<key>"
  // For file:// origin it's rewritten as "_file://"
  const s = buf.toString('utf8');
  return s.replace(/\x00/g, '\\x00').replace(/\x01/g, '\\x01');
}

function formatValue(buf) {
  const s = buf.toString('utf8');
  // Try JSON parse
  try {
    const j = JSON.parse(s);
    return JSON.stringify(j);
  } catch (_) {}
  // Strip the leading \x01 prefix Chromium uses
  if (s.charCodeAt(0) === 1) return JSON.stringify(s.slice(1));
  return JSON.stringify(s);
}

(async () => {
  const opts = parseArgs();
  const dbPath = opts.path.startsWith('~') ? opts.path.replace('~', process.env.HOME) : opts.path;
  console.error(`[info] opening ${dbPath}`);

  const db = new ClassicLevel(dbPath, { valueEncoding: 'binary' });
  await db.open();

  let count = 0;
  for await (const [k, v] of db.iterator()) {
    const keyStr = decodeKey(k);
    const valStr = opts.raw ? v.toString('hex') : formatValue(v);
    if (opts.keysPattern && !opts.keysPattern.test(keyStr)) continue;
    console.log(`${keyStr}\n  => ${valStr}`);
    count++;
  }

  console.error(`[info] ${count} key(s) printed`);
  await db.close();
})().catch(e => { console.error('[err]', e); process.exit(1); });
