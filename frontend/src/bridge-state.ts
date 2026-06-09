import type { BridgeEnvelope, JsonRecord } from "./bridge";

export type CurrentBridgeState = {
  sessionId?: string;
  sessionJobId?: string;
  analysisJobId?: string;
  modelDownloadJobId?: string;
};

export type ModelDownloadSummary = {
  status: string;
  failed: JsonRecord[];
};

const JOB_SCOPED_STATUS_EVENTS = new Set(["analysis.status", "template.status", "model.status"]);

export function initialSessionProgressText(): string {
  return "等待帧";
}

export function isBridgeEventForCurrentState(event: BridgeEnvelope, state: CurrentBridgeState): boolean {
  const eventName = event.event ?? "";
  const isSessionScoped = eventName.startsWith("session.") || eventName === "record.status";
  if (isSessionScoped) {
    return Boolean(state.sessionId && event.sessionId === state.sessionId);
  }

  const isJobScoped =
    eventName.startsWith("job.") ||
    eventName.endsWith(".progress") ||
    JOB_SCOPED_STATUS_EVENTS.has(eventName);
  if (isJobScoped) {
    return Boolean(event.jobId && isKnownJobId(event.jobId, state));
  }
  return true;
}

export function shouldApplySessionStartResponse(
  state: CurrentBridgeState,
  pendingSessionId: string,
  pendingJobId: string
): boolean {
  return state.sessionId === pendingSessionId && state.sessionJobId === pendingJobId;
}

export function shouldApplyModelDownloadStartResponse(state: CurrentBridgeState, pendingJobId: string): boolean {
  return state.modelDownloadJobId === pendingJobId;
}

export function shouldRenderPreviewFrameAt(
  nowMs: number,
  lastRenderedAtMs: number,
  minIntervalMs: number
): boolean {
  return nowMs - lastRenderedAtMs >= minIntervalMs;
}

export function progressTextForSessionStatus(payload: JsonRecord): string | null {
  if (String(payload.state ?? "") !== "running") {
    return null;
  }
  const totalFrames = finiteNumber(payload.totalFrames);
  if (totalFrames == null || totalFrames <= 0) {
    return "实时流";
  }
  return `0/${totalFrames} (0.0%)`;
}

export function progressTextForFrameProgress(progress: unknown): string | null {
  const progressRecord = asRecord(progress);
  if (!progressRecord) {
    return null;
  }
  const done = finiteNumber(progressRecord.done) ?? 0;
  const total = finiteNumber(progressRecord.total) ?? 0;
  const percent = finiteNumber(progressRecord.percent);
  if (percent != null) {
    return `${done}/${total} (${percent.toFixed(1)}%)`;
  }
  return `${done} 帧 / 实时`;
}

export function modelDownloadStatusFromPayload(payload: JsonRecord): ModelDownloadSummary | null {
  const state = String(payload.state ?? "");
  const failed = arrayOfRecords(payload.failed);
  if (state === "stopped") {
    return { status: "已取消", failed };
  }
  if (state === "failed" || failed.length > 0) {
    return { status: `下载失败：${formatFailedModels(failed)}`, failed };
  }
  if (state === "completed") {
    return { status: "下载完成", failed };
  }
  return null;
}

export function modelDownloadStatusFromJobEvent(event: BridgeEnvelope): ModelDownloadSummary {
  if (event.event === "job.stopped") {
    return { status: "已取消", failed: [] };
  }
  if (event.event === "job.failed") {
    const result = asRecord(event.payload.result) ?? event.payload;
    const failed = arrayOfRecords(result.failed);
    if (failed.length > 0) {
      return { status: `下载失败：${formatFailedModels(failed)}`, failed };
    }
    return { status: `下载失败：${event.error?.message ?? "未知错误"}`, failed: [] };
  }
  const result = asRecord(event.payload.result) ?? event.payload;
  return modelDownloadStatusFromPayload(result) ?? { status: "下载完成", failed: [] };
}

export function sessionStatusFromJobEvent(event: BridgeEnvelope): string | null {
  if (event.event === "job.failed") {
    return "运行失败";
  }
  if (event.event === "job.completed" || event.event === "job.stopped") {
    return "已停止";
  }
  return null;
}

function isKnownJobId(eventJobId: string, state: CurrentBridgeState): boolean {
  return (
    eventJobId === state.sessionJobId ||
    eventJobId === state.analysisJobId ||
    eventJobId === state.modelDownloadJobId
  );
}

function asRecord(value: unknown): JsonRecord | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as JsonRecord;
  }
  return null;
}

function arrayOfRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => asRecord(item) !== null) : [];
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function formatFailedModels(failed: JsonRecord[]): string {
  if (failed.length === 0) {
    return "未知错误";
  }
  return failed
    .map((item) => {
      const key = String(item.key ?? item.modelKey ?? "unknown");
      const error = String(item.error ?? "未知错误");
      return `${key} ${error}`;
    })
    .join("；");
}
