// Rewrites storyboard.json in a compact, diff-friendly layout: one line per step.
//   node scripts/pitch_video/format_storyboard.mjs
import {readFileSync, writeFileSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
const file = join(dirname(fileURLToPath(import.meta.url)), "storyboard.json");
const board = JSON.parse(readFileSync(file, "utf8"));
const one = (value) => JSON.stringify(value);
const lines = ["{"];
const top = Object.entries(board).filter(([key]) => key !== "scenes");
for (const [key, value] of top) lines.push(`  ${one(key)}: ${one(value)},`);
lines.push('  "scenes": [');
board.scenes.forEach((scene, index) => {
  lines.push("    {");
  const entries = Object.entries(scene);
  entries.forEach(([key, value], i) => {
    const comma = i < entries.length - 1 ? "," : "";
    if (Array.isArray(value) && value.length && typeof value[0] === "object") {
      lines.push(`      ${one(key)}: [`);
      value.forEach((item, j) => lines.push(`        ${one(item)}${j < value.length - 1 ? "," : ""}`));
      lines.push(`      ]${comma}`);
    } else if (key === "slide") {
      lines.push(`      "slide": {`);
      const slideEntries = Object.entries(value);
      slideEntries.forEach(([k, v], j) => {
        const c = j < slideEntries.length - 1 ? "," : "";
        if (Array.isArray(v) && v.length && typeof v[0] === "object") {
          lines.push(`        ${one(k)}: [`);
          v.forEach((item, n) => lines.push(`          ${one(item)}${n < v.length - 1 ? "," : ""}`));
          lines.push(`        ]${c}`);
        } else lines.push(`        ${one(k)}: ${one(v)}${c}`);
      });
      lines.push(`      }${comma}`);
    } else lines.push(`      ${one(key)}: ${one(value)}${comma}`);
  });
  lines.push(`    }${index < board.scenes.length - 1 ? "," : ""}`);
});
lines.push("  ]", "}", "");
const text = lines.join("\n");
JSON.parse(text);
writeFileSync(file, text);
console.log(`formatted ${board.scenes.length} scenes`);
