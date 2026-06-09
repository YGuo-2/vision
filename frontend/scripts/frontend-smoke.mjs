import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function read(path) {
  return readFileSync(join(root, path), "utf8");
}

function assertIncludes(source, marker, label) {
  if (!source.includes(marker)) {
    throw new Error(`${label} is missing required marker: ${marker}`);
  }
}

const app = read("src/App.vue");
const bridge = read("src/bridge.ts");
const tauri = read("src-tauri/src/lib.rs");

for (const marker of [
  "sourceKind === 'none'",
  "shouldApplyBridgeEvent",
  "setRawJson(event)",
  "template.create",
  "analysis.run",
  "model.download",
  "model.progress",
  "selectRecordDir",
  "选择目录",
  "downloadAllMissing",
  "cancelModelDownload",
]) {
  assertIncludes(app, marker, "App.vue");
}

for (const marker of ["selectDirectory", "invoke<string | null>(\"select_directory\")"]) {
  assertIncludes(bridge, marker, "bridge.ts");
}

for (const marker of ["select_directory", "SHBrowseForFolderW", "SHGetPathFromIDListW"]) {
  assertIncludes(tauri, marker, "src-tauri lib.rs");
}

console.log("Frontend smoke checks passed.");
