import { execFile } from 'node:child_process';
import { resolve } from 'node:path';
import { promisify } from 'node:util';

const run = promisify(execFile);
const ROOT = resolve(__dirname, '..', '..', '..');

/**
 * Runs the price refresh once inside the stack's worker container, the same code the daily job
 * runs (`python -m mtgvault.worker --once`). `E2E_WORKER_CMD` replaces the whole command line for
 * a stack started with other compose files or another project name.
 */
export async function runWorkerOnce(): Promise<{ code: number; output: string }> {
  const custom = process.env['E2E_WORKER_CMD'];
  const [command, ...args] = custom
    ? custom.split(' ')
    : [
        'docker',
        'compose',
        '-f',
        'deploy/compose.yaml',
        '-f',
        'deploy/compose.e2e.yaml',
        'exec',
        '-T',
        'worker',
        'python',
        '-m',
        'mtgvault.worker',
        '--once',
      ];
  try {
    const { stdout, stderr } = await run(command, args, { cwd: ROOT, timeout: 120_000 });
    return { code: 0, output: stdout + stderr };
  } catch (error) {
    const failure = error as { code?: number; stdout?: string; stderr?: string };
    return {
      code: typeof failure.code === 'number' ? failure.code : 1,
      output: `${failure.stdout}${failure.stderr}`,
    };
  }
}

export async function workerIsAvailable(): Promise<boolean> {
  const { output } = await runWorkerOnceCheck();
  return !/no such service|not running|executable file not found/i.test(output);
}

async function runWorkerOnceCheck(): Promise<{ output: string }> {
  try {
    const { stdout, stderr } = await run(
      'docker',
      [
        'compose',
        '-f',
        'deploy/compose.yaml',
        '-f',
        'deploy/compose.e2e.yaml',
        'ps',
        '--status',
        'running',
        'worker',
      ],
      { cwd: ROOT, timeout: 30_000 },
    );
    return { output: /worker/.test(stdout) ? '' : `not running ${stdout}${stderr}` };
  } catch (error) {
    return { output: String(error) };
  }
}
