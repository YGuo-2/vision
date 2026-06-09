import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Buffer } from "node:buffer";
import { parse } from "@vue/compiler-sfc";
import ts from "typescript";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function read(path) {
  return readFileSync(join(root, path), "utf8");
}

function assert(condition, label) {
  if (!condition) {
    throw new Error(label);
  }
}

function assertIncludes(source, marker, label) {
  assert(source.includes(marker), `${label} is missing required marker: ${marker}`);
}

function assertTemplateBinding(template, handler, label = handler) {
  const binding = new RegExp(`@click="[^"]*\\b${handler}\\b[^"]*"`);
  assert(binding.test(template), `App.vue template is missing @click binding for ${label}`);
}

async function importTypeScriptModule(path) {
  const source = read(path);
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove,
      verbatimModuleSyntax: false
    }
  });
  const encoded = Buffer.from(transpiled.outputText, "utf8").toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

const app = read("src/App.vue");
const bridge = read("src/bridge.ts");
const bridgeLifecycleSource = read("src/bridge-lifecycle.ts");
const bridgeStateSource = read("src/bridge-state.ts");
const tauri = read("src-tauri/src/lib.rs");
const { descriptor } = parse(app, { filename: "App.vue" });
const template = descriptor.template?.content ?? "";
const bridgeLifecycle = await importTypeScriptModule("src/bridge-lifecycle.ts");
const bridgeState = await importTypeScriptModule("src/bridge-state.ts");

for (const marker of [
  "sourceKind === 'none'",
  "shouldApplyBridgeEvent",
  "setRawJson(event)",
  "template.create",
  "analysis.run",
  "model.download",
  "model.progress",
  "model.status",
  "selectRecordDir",
  "选择目录",
  "downloadAllMissing",
  "cancelModelDownload",
  "stopActiveJobsBeforeUnmount",
  "stopJobById(sendBridgeCommand, modelDownloadJobId.value)"
]) {
  assertIncludes(app, marker, "App.vue");
}

for (const handler of [
  "startSession",
  "stopSession",
  "toggleRecord",
  "stopRecord",
  "selectRecordDir",
  "createTemplate",
  "runAnalysis",
  "stopAnalysisJob",
  "refreshModels",
  "downloadAllMissing",
  "cancelModelDownload",
  "downloadModel"
]) {
  assertTemplateBinding(template, handler);
}

for (const marker of ["selectDirectory", "invoke<string | null>(\"select_directory\")"]) {
  assertIncludes(bridge, marker, "bridge.ts");
}

for (const marker of ["select_directory", "OleInitialize", "OleUninitialize", "SHBrowseForFolderW", "SHGetPathFromIDListW"]) {
  assertIncludes(tauri, marker, "src-tauri lib.rs");
}

for (const marker of [
  "isBridgeEventForCurrentState",
  "progressTextForSessionStatus",
  "modelDownloadStatusFromJobEvent",
  "JOB_SCOPED_STATUS_EVENTS"
]) {
  assertIncludes(bridgeStateSource, marker, "bridge-state.ts");
}

for (const marker of ["stopJobById", "command: \"job.stop\"", "payload: { jobId: string }"]) {
  assertIncludes(bridgeLifecycleSource, marker, "bridge-lifecycle.ts");
}

const currentState = {
  sessionId: "session-current",
  sessionJobId: "job-session",
  analysisJobId: "job-analysis",
  modelDownloadJobId: "job-model"
};

assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "session.frame", sessionId: "session-old", jobId: "job-session", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "foreign session.frame must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "session.frame", jobId: "job-session", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "missing-id session.frame must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "record.status", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "missing-id record.status must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "record.status", sessionId: "session-current", payload: {}, error: null, timestamp: "" },
    currentState
  ) === true,
  "current record.status must be accepted"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "analysis.status", jobId: "job-old", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "foreign analysis.status must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "template.status", jobId: "job-old", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "foreign template.status must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "model.status", jobId: "job-old", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "foreign model.status must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "job.completed", payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "missing-id job.completed must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "job.completed", jobId: null, sessionId: null, payload: {}, error: null, timestamp: "" },
    currentState
  ) === false,
  "null-id job.completed must be ignored"
);
assert(
  bridgeState.isBridgeEventForCurrentState(
    { type: "event", event: "analysis.status", jobId: "job-analysis", payload: {}, error: null, timestamp: "" },
    currentState
  ) === true,
  "preassigned current analysis.status must be accepted before response"
);

assert(bridgeState.initialSessionProgressText() === "等待帧", "startup progress must not be 0%");
assert(
  bridgeState.progressTextForSessionStatus({ state: "running", totalFrames: 0 }) === "实时流",
  "unknown-total running status must display live-stream text"
);
assert(
  bridgeState.progressTextForFrameProgress({ done: 3, total: 0, percent: null }) === "3 帧 / 实时",
  "unknown-total frame progress must display live frame count"
);

const failedDownload = bridgeState.modelDownloadStatusFromJobEvent({
  type: "event",
  event: "job.completed",
  jobId: "job-model",
  payload: { result: { state: "failed", failed: [{ key: "pose_full", error: "network" }] } },
  error: null,
  timestamp: ""
});
assert(failedDownload.status.includes("下载失败"), "failed model download must be shown as failed");
assert(!failedDownload.status.includes("下载完成"), "failed model download must not be shown as completed");

const stopCalls = [];
const stoppedEnvelope = await bridgeLifecycle.stopJobById(async (command, payload, options) => {
  stopCalls.push({ command, payload, options });
  return {
    type: "response",
    requestId: "req-stop",
    ok: true,
    jobId: options.jobId,
    payload: { stopped: true },
    error: null,
    timestamp: ""
  };
}, "job-model");
assert(stopCalls.length === 1, "active model download unmount helper must send exactly one stop command");
assert(stopCalls[0].command === "job.stop", "active model download unmount helper must call job.stop");
assert(stopCalls[0].payload.jobId === "job-model", "active model download unmount helper must stop exact job payload");
assert(stopCalls[0].options.jobId === "job-model", "active model download unmount helper must stop exact job options");
assert(stoppedEnvelope?.jobId === "job-model", "active model download unmount helper must return stop envelope");

let emptyStopCalled = false;
const skippedStop = await bridgeLifecycle.stopJobById(async () => {
  emptyStopCalled = true;
  throw new Error("empty job id must not call job.stop");
}, undefined);
assert(skippedStop === null, "empty model download job id must skip stop command");
assert(emptyStopCalled === false, "empty model download job id must not call bridge");

const rawEnvelope = {
  type: "event",
  event: "session.status",
  jobId: "job-session",
  sessionId: "session-current",
  payload: { state: "running" },
  error: null,
  timestamp: "2026-06-09T00:00:00Z"
};
const rawJson = JSON.stringify(rawEnvelope, null, 2);
assert(rawJson.includes("\"jobId\": \"job-session\""), "raw JSON must keep jobId");
assert(rawJson.includes("\"sessionId\": \"session-current\""), "raw JSON must keep sessionId");

console.log("Frontend behavior smoke checks passed.");
