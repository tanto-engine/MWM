// Compile only the UI: this command never creates a distributable EXE.
// Engine's release gate must stage and pin the worker before portable packaging.
// Keep generated Chromium code outside tracked source so reviews show authored changes.
import { build } from 'esbuild';
import { mkdir, copyFile, readFile, writeFile, readdir, rm } from 'node:fs/promises';
await mkdir('desktop-dist', { recursive: true });
await rm('desktop-dist/assets/background.png', { force: true });
for (const file of ['main.cjs', 'preload.cjs', 'portable_worker.cjs', 'smoke.cjs', 'index.html', 'style.css']) await copyFile('desktop/' + file, 'desktop-dist/' + file);
await build({ entryPoints: ['desktop/renderer.ts'], bundle: true, outfile: 'desktop-dist/renderer.js', target: 'chrome140' });
// Bundle the complete readable collection; raw evidence ZIPs stay in the private repository.
// Paths are derived from the curated taxonomy, never from renderer-supplied filenames.
// Research entries remain separate from Engine's playable capability menu.
const manifest = JSON.parse(await readFile('dataset/dataset.json', 'utf8'));
const moves = [];
for (const weapon of Object.keys(manifest.weapons)) for (const boss of Object.keys(manifest.bosses)) {
  const directory = `dataset/weapons/${weapon}/${boss}`;
  let files;
  try { files = await readdir(directory); } catch (error) { if (error.code === 'ENOENT') continue; throw error; }
  for (const file of files.filter(file => file.endsWith('.json')).sort()) moves.push(JSON.parse(await readFile(`${directory}/${file}`, 'utf8')));
}
const design = JSON.parse(await readFile('configurations/sword-rebuild-1.json', 'utf8'));
const intake = JSON.parse(await readFile('dataset/intake.json', 'utf8'));
await writeFile('desktop-dist/collection.json', JSON.stringify({ manifest, moves, design, intake }));
