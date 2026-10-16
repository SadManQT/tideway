// Syntax-check every maintained browser/automation JS module without packages.
// Browser workflow tests exercise behavior; this catches parse errors in files
// that the selected demo story may not load.
import {readdirSync} from 'node:fs';
import {join, dirname, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
function sources(directory) {
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const path = join(directory, entry.name);
    if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') return sources(path);
    return entry.isFile() && /\.(?:js|mjs)$/.test(entry.name) ? [path] : [];
  });
}

const files = ['web', 'scripts'].flatMap(folder => sources(join(root, folder))).sort();
for (const path of files) {
  const result = spawnSync(process.execPath, ['--check', path], {encoding: 'utf8', windowsHide: true});
  if (result.error || result.status !== 0) {
    console.error(`JavaScript syntax failed: ${relative(root, path)}`);
    console.error(result.error?.message || result.stderr || result.stdout);
    process.exit(result.status || 1);
  }
}
console.log(`JavaScript syntax passed: ${files.length} files.`);
