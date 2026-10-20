#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const version = require('../package.json').version;

function run(command, args, options = {}) {
  return spawnSync(command, args, {windowsHide: true, ...options});
}

function findPython() {
  const candidates = [
    ...(process.env.SPEIIHOSTING_PYTHON ? [[process.env.SPEIIHOSTING_PYTHON, []]] : []),
    ...(process.platform === 'win32' ? [['py', ['-3']]] : []),
    ['python3', []], ['python', []],
  ];
  return candidates.find(([command, prefix]) => run(command, [...prefix, '-c',
    'import sys; raise SystemExit(sys.version_info < (3,10))']).status === 0);
}

function main() {
  const python = findPython();
  if (!python) {
    console.error('SpeiiHosting requires Python 3.10+. Install Python or use scripts/install.sh / install.ps1.');
    return 1;
  }
  let [command, prefix] = python;
  const check = 'import importlib.metadata as m; raise SystemExit(m.version("speiihosting") != ' + JSON.stringify(version) + ')';
  if (run(command, [...prefix, '-c', check], {stdio: 'ignore'}).status !== 0) {
    const home = process.env.SPEIIHOSTING_HOME || path.join(os.homedir(), '.speiihosting');
    fs.mkdirSync(home, {recursive: true, mode: 0o700});
    const environment = path.join(home, 'cli-venv');
    const interpreter = path.join(environment, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    const lock = path.join(home, 'npm-install.lock');
    try {
      fs.mkdirSync(lock);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      console.error('Another installation may be running. Retry; if it was interrupted, remove ' + lock);
      return 1;
    }
    try {
      if (!fs.existsSync(interpreter)) {
        const result = run(command, [...prefix, '-m', 'venv', environment], {stdio: 'inherit'});
        if (result.status !== 0) return result.status || 1;
      }
      command = interpreter;
      prefix = [];
      if (run(command, ['-c', check], {stdio: 'ignore'}).status !== 0) {
        console.error('Installing the Python core into ' + environment);
        const root = path.resolve(__dirname, '..');
        const result = run(command, ['-m', 'pip', 'install', '--upgrade', root], {stdio: 'inherit'});
        if (result.status !== 0) return result.status || 1;
      }
    } finally {
      fs.rmdirSync(lock);
    }
  }
  const result = run(command, [...prefix, '-m', 'speiihosting', ...process.argv.slice(2)], {stdio: 'inherit'});
  if (result.error) console.error(result.error.message);
  return result.status === null ? 1 : result.status;
}

if (require.main === module) {
  try { process.exitCode = main(); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = {findPython};
