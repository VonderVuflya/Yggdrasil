#!/usr/bin/env node
'use strict';

/*
 * Yggdrasil npm launcher.
 *
 * Yggdrasil's engine is pure Python. This package is a thin launcher: it makes
 * sure a runner is available (prefers `uv`/`uvx`, which can fetch a managed
 * Python on its own), then runs the published Python package `yggdrasil-memory`
 * and forwards every argument. So `npx yggdrasil-memory install` works even on
 * a machine without Python.
 *
 * Env overrides:
 *   YGG_NPM_SOURCE   install source for uvx/pipx (default: "yggdrasil-memory").
 *                    Use a wheel path or "git+https://github.com/VonderVuflya/yggdrasil.git" to test.
 *   YGG_NO_BOOTSTRAP set to "1" to never auto-install uv.
 */

const { spawnSync } = require('child_process');
const os = require('os');
const path = require('path');

const SOURCE = process.env.YGG_NPM_SOURCE || 'yggdrasil-memory';
const args = process.argv.slice(2);

function has(cmd) {
  const r = spawnSync(cmd, ['--version'], { stdio: 'ignore' });
  return !r.error && r.status === 0;
}

function run(cmd, cmdArgs) {
  const r = spawnSync(cmd, cmdArgs, { stdio: 'inherit' });
  if (r.error) return null;
  return r.status === null ? 1 : r.status;
}

function ensureUv() {
  if (process.env.YGG_NO_BOOTSTRAP === '1') return false;
  process.stderr.write(
    'yggdrasil: uv not found — installing it once via https://astral.sh/uv ...\n'
  );
  const r = process.platform === 'win32'
    ? spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'ByPass', '-Command',
        'irm https://astral.sh/uv/install.ps1 | iex'], { stdio: 'inherit' })
    : spawnSync('sh', ['-c', 'curl -LsSf https://astral.sh/uv/install.sh | sh'], { stdio: 'inherit' });
  return !r.error && r.status === 0;
}

function freshUvBin() {
  // uv's installer drops the binary in ~/.local/bin by default.
  const home = os.homedir();
  return process.platform === 'win32'
    ? path.join(home, '.local', 'bin', 'uv.exe')
    : path.join(home, '.local', 'bin', 'uv');
}

let code = null;
if (has('uvx')) {
  code = run('uvx', ['--from', SOURCE, 'ygg', ...args]);
} else if (has('uv')) {
  code = run('uv', ['tool', 'run', '--from', SOURCE, 'ygg', ...args]);
} else if (has('pipx')) {
  code = run('pipx', ['run', '--spec', SOURCE, 'ygg', ...args]);
} else if (ensureUv()) {
  // PATH in this process may not see the freshly installed uv yet — call it directly.
  code = run(freshUvBin(), ['tool', 'run', '--from', SOURCE, 'ygg', ...args]);
  if (code === null && has('uv')) {
    code = run('uv', ['tool', 'run', '--from', SOURCE, 'ygg', ...args]);
  }
}

if (code === null) {
  process.stderr.write(
    '\nyggdrasil: could not find or bootstrap a runner.\n' +
    'Install one of these, then re-run:\n' +
    '  - uv    https://docs.astral.sh/uv/   (recommended; handles Python for you)\n' +
    '  - pipx  https://pipx.pypa.io/\n' +
    'Or install the Python package directly:  pip install yggdrasil-memory\n'
  );
  process.exit(1);
}
process.exit(code);
