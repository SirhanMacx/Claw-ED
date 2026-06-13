#!/usr/bin/env node
import { readdir, readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP = join(dirname(fileURLToPath(import.meta.url)), '..');
const SETS = [
  { out: join(APP, 'app-store/screenshots/iphone-6.9'), width: 1290, height: 2796 },
  { out: join(APP, 'app-store/screenshots/ipad-12.9'), width: 2048, height: 2732 },
];

function pngSize(buf) {
  if (buf.toString('ascii', 1, 4) !== 'PNG') throw new Error('not a png');
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

const results = [];
for (const set of SETS) {
  const files = (await readdir(set.out)).filter((file) => file.endsWith('.png')).sort();
  if (files.length < 5) throw new Error(`expected at least 5 screenshots in ${set.out}, found ${files.length}`);

  for (const file of files) {
    const size = pngSize(await readFile(join(set.out, file)));
    if (size.width !== set.width || size.height !== set.height) {
      throw new Error(`${file} is ${size.width}x${size.height}, expected ${set.width}x${set.height}`);
    }
  }
  results.push({ outDir: set.out, screenshots: files.length, size: `${set.width}x${set.height}` });
}

console.log(JSON.stringify({ ok: true, sets: results }, null, 2));
