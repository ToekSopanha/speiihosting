const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');

test('npm launcher forwards commands to the installed Python core', () => {
  const python = process.env.SPEIIHOSTING_PYTHON || path.resolve('.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const result = spawnSync(process.execPath, ['bin/speiihos.cjs', '--version'], {
    encoding: 'utf8', env: {...process.env, SPEIIHOSTING_PYTHON: python},
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), require('../package.json').version);
});
