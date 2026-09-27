// Compile only the UI: this command never creates a distributable EXE.
// Engine's release gate must stage and pin the worker before portable packaging.
// Keep generated Chromium code outside tracked source so reviews show authored changes.
import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('desktop-dist', { recursive: true });
for (const file of ['main.cjs', 'preload.cjs', 'index.html', 'style.css']) await copyFile('desktop/' + file, 'desktop-dist/' + file);
await build({ entryPoints: ['desktop/renderer.ts'], bundle: true, outfile: 'desktop-dist/renderer.js', target: 'chrome140' });
