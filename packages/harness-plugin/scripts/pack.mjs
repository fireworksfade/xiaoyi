import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const destination = fileURLToPath(new URL('../../../output/', import.meta.url));
await mkdir(destination, { recursive: true });
const packed = spawnSync(process.execPath, [process.env.npm_execpath, 'pack', '--pack-destination', destination, '--json'], { encoding: 'utf8' });
if (packed.status !== 0) { process.stderr.write(packed.stderr); process.exit(packed.status ?? 1); }
const [metadata] = JSON.parse(packed.stdout);
const digest = createHash('sha256').update(await readFile(join(destination, metadata.filename))).digest('hex');
await writeFile(join(destination, `${metadata.filename}.sha256`), `${digest}  ${metadata.filename}\n`);
console.log(`Plugin package: ${join(destination, metadata.filename)}\nSHA-256: ${digest}\n${metadata.entryCount} files, ${metadata.size} bytes`);
