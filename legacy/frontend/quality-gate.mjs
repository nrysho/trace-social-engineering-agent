import { spawn } from 'node:child_process';

// No shell, no browser-controlled executable, bounded time and output.
export function checkQuality(request, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PERSON5_PYTHON || 'python', ['-m', 'quality.node_gate'],
      { cwd, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '', settled = false;
    const fail = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.kill();
      reject(Object.assign(new Error('Quality validator unavailable; no submission sent.'), { status: 503 }));
    };
    const timer = setTimeout(fail, 10000);
    child.on('error', fail);
    child.stdin.on('error', fail);
    child.stderr.on('data', () => {});
    child.stdout.on('data', data => {
      output += data;
      if (output.length > 200000) fail();
    });
    child.on('close', code => {
      if (settled) return;
      let qa;
      try { qa = JSON.parse(output); } catch { return fail(); }
      if (code !== 0 || typeof qa.passed !== 'boolean' ||
          !Array.isArray(qa.errors) || !Array.isArray(qa.warnings) ||
          ![...qa.errors, ...qa.warnings].every(x => typeof x === 'string') ||
          qa.passed !== (qa.errors.length === 0)) return fail();
      settled = true;
      clearTimeout(timer);
      if (!qa.passed) return reject(Object.assign(new Error('Quality gate blocked submission.'), { status: 422, detail: { qa } }));
      resolve(qa);
    });
    child.stdin.end(JSON.stringify(request));
  });
}
