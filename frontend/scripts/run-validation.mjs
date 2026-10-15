// Uses Vite's existing compiler and Node's built-in test runner; no test package.
import { build } from 'vite';
import { spawnSync } from 'node:child_process';

await build({
  configFile: false,
  logLevel: 'warn',
  build: {
    ssr: 'scripts/verify-integration.tsx',
    outDir: '.validation',
    rollupOptions: { output: { entryFileNames: 'verify.mjs' } },
  },
});
const result = spawnSync(process.execPath, ['--test', '.validation/verify.mjs'], {
  stdio: 'inherit', env: process.env,
});
process.exitCode = result.status ?? 1;
