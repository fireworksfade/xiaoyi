import { build } from 'esbuild';
import { mkdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
await mkdir('lib', { recursive: true });
const result = spawnSync(process.execPath, ['../../node_modules/typescript/bin/tsc', '-p', 'tsconfig.json'], { stdio: 'inherit' });
if (result.status !== 0) process.exit(result.status ?? 1);
await build({ entryPoints: ['src/index.ts'], outfile: 'lib/index.js', bundle: true, platform: 'node', format: 'esm', packages: 'external', target: 'node22' });
await build({
  entryPoints: ['src/client/index.tsx'], outfile: 'lib/client.js', bundle: true,
  platform: 'browser', format: 'cjs', packages: 'external', target: 'es2022',
  banner: { js: 'window.__ModuleLoader__.load({id:"@xiaoyi/dsh-iot",factory:(require)=>{var module={exports:{}};var exports=module.exports;' },
  footer: { js: 'return module.exports;}});' }
});
console.log('Built Xiaoyi IoT host and Desktop client for Harness 0.2.0-rc.2.');
