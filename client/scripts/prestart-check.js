#!/usr/bin/env node
/**
 * Simple guard that ensures the CRA dev server port is free before running react-scripts.
 * Prevents confusing hangs when another process already occupies the port.
 */
const net = require('net');
const { spawnSync } = require('child_process');

const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 3000);
const timeoutMs = Number(process.env.PORT_GUARD_TIMEOUT_MS || 1200);
const skip = process.env.SKIP_PORT_GUARD === '1' || process.argv.includes('--skip');
const checkOnly = process.argv.includes('--check-only');

if (skip) {
  process.exit(0);
}

function findPidsUsingPort(targetPort) {
  try {
    if (process.platform === 'win32') {
      const result = spawnSync('cmd', ['/c', `netstat -ano | findstr :${targetPort}`], { encoding: 'utf8' });
      if (result.status !== 0) {
        return [];
      }
      const lines = result.stdout.split(/\r?\n/).filter(Boolean);
      const pids = new Set();
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        const pid = parts[parts.length - 1];
        if (pid) {
          pids.add(pid);
        }
      }
      return Array.from(pids);
    }
    const result = spawnSync('lsof', ['-nP', `-iTCP:${targetPort}`, '-sTCP:LISTEN'], { encoding: 'utf8' });
    if (result.status !== 0) {
      return [];
    }
    const lines = result.stdout.split(/\r?\n/).filter(Boolean);
    const pids = new Set();
    for (const line of lines.slice(1)) {
      const parts = line.trim().split(/\s+/);
      if (parts[1]) {
        pids.add(parts[1]);
      }
    }
    return Array.from(pids);
  } catch (err) {
    return [];
  }
}

function exitBusy() {
  const pids = findPidsUsingPort(port);
  const pidInfo = pids.length ? pids.join(', ') : 'unknown process';
  console.error(`\n[port-guard] Port ${port} appears to be in use by ${pidInfo}.`);
  console.error('[port-guard] Stop the process or free the port before running `npm start`.');
  console.error('[port-guard] To override temporarily, set SKIP_PORT_GUARD=1.');
  process.exit(1);
}

function checkPortFree() {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let resolved = false;
    const cleanup = () => {
      if (!resolved) {
        resolved = true;
        socket.destroy();
      }
    };
    socket.setTimeout(timeoutMs, () => {
      cleanup();
      resolve(true);
    });
    socket.once('error', (err) => {
      cleanup();
      // ECONNREFUSED => nothing is listening (what we want)
      if (err.code === 'ECONNREFUSED' || err.code === 'EHOSTUNREACH' || err.code === 'ENOTFOUND') {
        resolve(true);
        return;
      }
      // Any other error treat as unknown/busy
      resolve(false);
    });
    socket.connect({ host, port }, () => {
      cleanup();
      resolve(false);
    });
  });
}

(async () => {
  const free = await checkPortFree();
  if (!free) {
    exitBusy();
  }
  if (checkOnly) {
    console.log(`[port-guard] Port ${port} is free.`);
  }
})();
