<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  type BridgeEnvelope,
  type CameraEntry,
  type JsonRecord,
  type RecordState,
  fetchLatestFrameBytes,
  listenBridgeEvents,
  selectDirectory,
  sendBridgeCommand
} from "./bridge";
import { stopJobById } from "./bridge-lifecycle";
import {
  type FrameIdentity,
  initialSessionProgressText,
  isCurrentFrameIdentity,
  isBridgeEventForCurrentState,
  modelDownloadStatusFromJobEvent,
  modelDownloadStatusFromPayload,
  progressTextForFrameProgress,
  progressTextForSessionStatus,
  sanitizedRawEnvelope,
  shouldApplyModelDownloadStartResponse,
  shouldApplySessionStartResponse,
  sessionStartFailureState,
  sessionStatusFromJobEvent
} from "./bridge-state";

type SourceKind = "none" | "camera" | "video";

type ModelItem = {
  key: string;
  label: string;
  installed: boolean;
  active: boolean;
  category?: string;
  profile?: string;
  downloadable?: boolean;
  installedSupported?: boolean;
  runtimeSupported?: boolean;
  defaultRouteEligible?: boolean;
  note?: string;
  license?: string;
  purpose?: string;
  proxy?: string;
  offlineInstall?: string;
  downloadHint?: string;
  path?: string;
  sizeMb?: number | null;
};

type SessionFramePayload = JsonRecord & {
  sessionId?: string;
  framePort?: number;
  frameToken?: string;
  frameId?: number;
  frameHandle?: string;
  actionsText?: string;
  fps?: number;
  frameIndex?: number;
  progress?: { done: number; total: number; percent: number | null };
};

type PendingFrame = {
  payload: SessionFramePayload;
  sessionId: string | null;
  jobId: string | null;
  frameId: number;
  frameHandle: string;
};

type AnalysisMode = "template" | "analysis";

type AnalysisProgress = {
  stage: string;
  done: number;
  total: number;
  percent: number | null;
};

type TechIndicatorRow = {
  key: string;
  label: string;
  status: string;
  reason: string;
  primaryCause: string;
  failedStage: string;
};

const cameras = ref<CameraEntry[]>([]);
const cameraIndex = ref<number>(0);
const sourceKind = ref<SourceKind>("camera");
const videoPath = ref("");
const poseVariant = ref<"lite" | "full" | "heavy">("lite");
const workers = ref(1);
const enableHands = ref(false);
const recordDir = ref("");
const defaultRecordDir = "Python outputs_dir()";

const statusText = ref("就绪");
const actionsText = ref("-");
const fpsText = ref("--");
const progressText = ref("等待开始");
const fallbackNotice = ref("");
const reviewNotice = ref("");
const previewCanvas = ref<HTMLCanvasElement | null>(null);
const frameIndex = ref(0);
const isRunning = ref(false);
const sessionId = ref<string | undefined>();
const jobId = ref<string | undefined>();
const errorText = ref("");
const rawJson = ref("{}");

const showAnalysisPanel = ref(false);
const baseVideo = ref("");
const templatePath = ref("");
const templateOut = ref("");
const targetVideo = ref("");
const analysisStartFrame = ref("");
const analysisEndFrame = ref("");
const analysisWorkers = ref(1);
const previewOut = ref("");
const doCompare = ref(true);
const doTechEval = ref(false);
const highQualityBodyOnly = ref(false);
const stance = ref<"left" | "right">("left");
const viewHint = ref<"auto" | "front" | "side" | "mixed">("auto");
const debugVideo = ref(false);
const debugVideoPath = ref("");
const analysisJobId = ref<string | undefined>();
const analysisMode = ref<AnalysisMode>("analysis");
const analysisStatus = ref("未运行");
const analysisProgress = ref<AnalysisProgress | null>(null);
const analysisResult = ref<JsonRecord | null>(null);

const recordState = ref<RecordState>({
  state: "idle",
  buttonText: "开始录制",
  stopEnabled: false,
  resultPath: null,
  framesWritten: 0,
  lastError: null
});

const models = ref<ModelItem[]>([]);
const missingModelKeys = ref<string[]>([]);
const modelsDir = ref("");
const yoloRuntimeMessage = ref("");
const showSettingsPanel = ref(false);
const modelDownloadJobId = ref<string | undefined>();
const modelDownloadStatus = ref("未下载");
const modelDownloadProgress = ref<AnalysisProgress | null>(null);

const sourceHint = computed(() => {
  if (sourceKind.value === "none") {
    return "当前输入源：未选择";
  }
  if (sourceKind.value === "camera") {
    return `当前输入源：摄像头 ${cameraIndex.value}`;
  }
  return videoPath.value ? `当前输入源：视频文件 ${videoPath.value}` : "当前输入源：未选择视频文件";
});

const canStart = computed(() => {
  if (isRunning.value) return false;
  if (sourceKind.value === "none") return false;
  if (sourceKind.value === "camera") return cameras.value.length > 0;
  return videoPath.value.trim().length > 0;
});

const activeModels = computed(() => models.value.filter((model) => model.active));
const missingActiveModels = computed(() => activeModels.value.filter((model) => !model.installed));

const compareResult = computed(() => {
  const result = analysisResult.value?.compare;
  return isJsonRecord(result) ? result : null;
});

const techEvalResult = computed(() => {
  const result = analysisResult.value?.techEval;
  return isJsonRecord(result) ? result : null;
});

const techIndicatorRows = computed<TechIndicatorRow[]>(() => {
  const indicators = techEvalResult.value?.indicators;
  if (!isJsonRecord(indicators)) return [];
  const labels: Record<string, string> = {
    cogFinal: "重心最终",
    cogSide: "侧向重心",
    cogFront: "正向重心",
    cogCom: "综合重心",
    retractSpeed: "回收速度",
    forceSequence: "发力顺序",
    wristAngle: "拳面角度"
  };
  return Object.entries(labels)
    .map(([key, label]) => {
      const item = indicators[key];
      if (!isJsonRecord(item)) return null;
      return {
        key,
        label,
        status: String(item.status ?? "-"),
        reason: String(item.reason ?? "-"),
        primaryCause: String(item.primaryCause ?? "-"),
        failedStage: String(item.failedStage ?? "-")
      };
    })
    .filter((item): item is TechIndicatorRow => item !== null);
});

let unlisten: (() => void) | undefined;
let pendingFrame: PendingFrame | null = null;
let latestFrameIdentity: FrameIdentity | null = null;
let frameRenderRaf: number | null = null;
let isRenderingFrame = false;
let lastDrawnFrameId = 0;

// 后台预热 MediaPipe pipeline，使点击「开始」时模型已就绪、首帧更快出现。
// 失败静默：预热只是优化，失败时正常流程会退回懒加载路径。
async function warmupPipeline(): Promise<void> {
  try {
    const response = await sendBridgeCommand("session.warmup", {
      poseVariant: poseVariant.value,
      enableHands: enableHands.value
    });
    if (!response.ok) {
      statusText.value = `预热未完成：${response.error?.message ?? "开始时加载模型"}`;
    }
  } catch (error) {
    statusText.value = `预热未完成：${errorMessage(error, "开始时加载模型")}`;
  }
}

onMounted(async () => {
  try {
    unlisten = await listenBridgeEvents(handleBridgeEvent);
  } catch (error) {
    errorText.value = errorMessage(error, "bridge 事件监听失败");
    return;
  }
  void refreshCameras().catch((error) => {
    errorText.value = errorMessage(error, "刷新摄像头失败");
  });
  void refreshModels()
    .catch((error) => {
      errorText.value = errorMessage(error, "刷新模型状态失败");
    })
    .finally(() => {
      void warmupPipeline();
    });
});

// pose 变体或手部开关变化时，缓存键失效，重新预热以匹配新配置。
watch([poseVariant, enableHands], () => {
  if (!isRunning.value) {
    void warmupPipeline();
  }
});

onBeforeUnmount(() => {
  stopActiveJobsBeforeUnmount();
  cancelPendingFrameRender();
  if (unlisten) unlisten();
});

async function refreshCameras(): Promise<void> {
  errorText.value = "";
  const response = await sendBridgeCommand("camera.list", { scanLimit: 5 });
  if (!response.ok) {
    errorText.value = response.error?.message ?? "刷新摄像头失败";
    return;
  }
  const payload = response.payload as unknown as { cameras: CameraEntry[] };
  cameras.value = payload.cameras ?? [];
  if (cameras.value.length > 0 && !cameras.value.some((camera) => camera.index === cameraIndex.value)) {
    cameraIndex.value = cameras.value[0].index;
  }
}

async function refreshModels(): Promise<void> {
  const response = await sendBridgeCommand("model.status", {
    poseVariant: poseVariant.value,
    enableHands: enableHands.value
  });
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "刷新模型状态失败";
    return;
  }
  const payload = response.payload as unknown as {
    modelsDir: string;
    models: ModelItem[];
    missingKeys: string[];
    yoloRuntime?: { message?: string };
  };
  modelsDir.value = payload.modelsDir ?? "";
  models.value = payload.models ?? [];
  missingModelKeys.value = payload.missingKeys ?? [];
  yoloRuntimeMessage.value = String(payload.yoloRuntime?.message ?? "");
}

async function downloadModel(modelKey: string): Promise<void> {
  const pendingJobId = nextBridgeId("model-job");
  modelDownloadJobId.value = pendingJobId;
  const response = await sendBridgeCommand("model.download", { modelKey }, { jobId: pendingJobId });
  setRawJson(response);
  if (!response.ok) {
    if (shouldApplyModelDownloadStartResponse({ modelDownloadJobId: modelDownloadJobId.value }, pendingJobId)) {
      modelDownloadJobId.value = undefined;
    }
    errorText.value = response.error?.message ?? "模型下载失败";
    return;
  }
  if (!shouldApplyModelDownloadStartResponse({ modelDownloadJobId: modelDownloadJobId.value }, pendingJobId)) {
    return;
  }
  modelDownloadJobId.value = response.jobId ?? pendingJobId;
  modelDownloadStatus.value = `下载中：${modelKey}`;
  modelDownloadProgress.value = null;
}

async function downloadAllMissing(): Promise<void> {
  const pendingJobId = nextBridgeId("model-job");
  modelDownloadJobId.value = pendingJobId;
  const response = await sendBridgeCommand("model.download", { allMissing: true }, { jobId: pendingJobId });
  setRawJson(response);
  if (!response.ok) {
    if (shouldApplyModelDownloadStartResponse({ modelDownloadJobId: modelDownloadJobId.value }, pendingJobId)) {
      modelDownloadJobId.value = undefined;
    }
    errorText.value = response.error?.message ?? "下载缺失模型失败";
    return;
  }
  if (!shouldApplyModelDownloadStartResponse({ modelDownloadJobId: modelDownloadJobId.value }, pendingJobId)) {
    return;
  }
  modelDownloadJobId.value = response.jobId ?? pendingJobId;
  modelDownloadStatus.value = "下载全部缺失模型中";
  modelDownloadProgress.value = null;
}

async function cancelModelDownload(): Promise<void> {
  const response = await stopJobById(sendBridgeCommand, modelDownloadJobId.value);
  if (!response) return;
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "取消模型下载失败";
    return;
  }
  modelDownloadStatus.value = "已取消";
  modelDownloadJobId.value = undefined;
  modelDownloadProgress.value = null;
}

function stopActiveJobsBeforeUnmount(): void {
  if (modelDownloadJobId.value) {
    void cancelModelDownload();
  }
  if (analysisJobId.value) {
    void stopAnalysisJob();
  }
  if (isRunning.value) {
    void stopSession();
  }
}

async function startSession(): Promise<void> {
  if (!canStart.value) return;
  errorText.value = "";
  statusText.value = "启动中…";
  actionsText.value = "-";
  fpsText.value = "--";
  fallbackNotice.value = "";
  reviewNotice.value = "";
  progressText.value = initialSessionProgressText();
  clearPreviewCanvas();
  cancelPendingFrameRender();
  frameIndex.value = 0;
  const pendingSessionId = nextBridgeId("session");
  const pendingJobId = nextBridgeId("session-job");
  sessionId.value = pendingSessionId;
  jobId.value = pendingJobId;
  const payload: JsonRecord = {
    sourceKind: sourceKind.value,
    poseVariant: poseVariant.value,
    workers: workers.value,
    enableHands: enableHands.value,
    modelAvailability: routeModelAvailability()
  };
  assignOptionalString(payload, "recordDir", recordDir.value);
  if (sourceKind.value === "camera") {
    payload.cameraIndex = cameraIndex.value;
  } else {
    payload.videoPath = videoPath.value.trim();
  }
  const response = await sendBridgeCommand("session.start", payload, {
    sessionId: pendingSessionId,
    jobId: pendingJobId
  });
  setRawJson(response);
  if (!response.ok) {
    const failure = sessionStartFailureState(response.error?.message);
    statusText.value = failure.statusText;
    isRunning.value = failure.isRunning;
    sessionId.value = failure.sessionId;
    jobId.value = failure.sessionJobId;
    errorText.value = failure.errorText;
    return;
  }
  if (!shouldApplySessionStartResponse({ sessionId: sessionId.value, sessionJobId: jobId.value }, pendingSessionId, pendingJobId)) {
    return;
  }
  isRunning.value = true;
  sessionId.value = response.sessionId ?? pendingSessionId;
  jobId.value = response.jobId ?? pendingJobId;
  applyBackendRouteNotice(response.payload.backendRoute);
}

async function stopSession(): Promise<void> {
  if (!sessionId.value && !jobId.value) return;
  statusText.value = "正在停止…";
  const response = await sendBridgeCommand("session.stop", { sessionId: sessionId.value ?? "", jobId: jobId.value ?? "" }, {
    sessionId: sessionId.value,
    jobId: jobId.value
  });
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "停止失败";
    return;
  }
  markSessionStopped("已停止");
}

async function toggleRecord(): Promise<void> {
  if (!sessionId.value || !isRunning.value) return;
  const response = await sendBridgeCommand<RecordState>("record.toggle", { sessionId: sessionId.value }, {
    sessionId: sessionId.value,
    jobId: jobId.value
  });
  if (response.ok) {
    applyRecordPayload(response.payload);
  }
}

async function stopRecord(): Promise<void> {
  if (!sessionId.value) return;
  const response = await sendBridgeCommand<RecordState>("record.stop", { sessionId: sessionId.value }, {
    sessionId: sessionId.value,
    jobId: jobId.value
  });
  if (response.ok) {
    applyRecordPayload(response.payload);
  }
}

async function selectRecordDir(): Promise<void> {
  const selected = await selectDirectory();
  if (selected) {
    recordDir.value = selected;
  }
}

async function createTemplate(): Promise<void> {
  if (!baseVideo.value.trim()) {
    errorText.value = "请先填写基准视频路径";
    return;
  }
  analysisMode.value = "template";
  analysisStatus.value = "模板生成中…";
  analysisProgress.value = null;
  errorText.value = "";
  const payload: JsonRecord = {
    baseVideo: baseVideo.value.trim(),
    poseVariant: poseVariant.value,
    workers: analysisWorkers.value,
    preview: false
  };
  assignOptionalString(payload, "outPath", templateOut.value);
  assignOptionalInt(payload, "startFrame", analysisStartFrame.value);
  assignOptionalInt(payload, "endFrame", analysisEndFrame.value);

  const pendingJobId = nextBridgeId("analysis-job");
  analysisJobId.value = pendingJobId;
  const response = await sendBridgeCommand("template.create", payload, { jobId: pendingJobId });
  setRawJson(response);
  if (!response.ok) {
    analysisStatus.value = "模板生成失败";
    analysisJobId.value = undefined;
    errorText.value = response.error?.message ?? "模板生成失败";
    return;
  }
  analysisJobId.value = response.jobId ?? pendingJobId;
}

async function runAnalysis(): Promise<void> {
  if (!targetVideo.value.trim()) {
    errorText.value = "请先填写目标视频路径";
    return;
  }
  if (doCompare.value && !templatePath.value.trim()) {
    errorText.value = "模板比对需要填写模板路径";
    return;
  }
  if (!doCompare.value && !doTechEval.value && !highQualityBodyOnly.value) {
    errorText.value = "请至少启用模板比对、直拳技术评估或高质量 body-only 分析";
    return;
  }
  analysisMode.value = "analysis";
  analysisStatus.value = "动作分析中…";
  analysisProgress.value = null;
  analysisResult.value = null;
  errorText.value = "";

  const payload: JsonRecord = {
    targetVideo: targetVideo.value.trim(),
    poseVariant: poseVariant.value,
    workers: analysisWorkers.value,
    doCompare: doCompare.value,
    doTechEval: doTechEval.value,
    enableHands: enableHands.value,
    qualityProfile: highQualityBodyOnly.value ? "high_quality" : "default",
    modelAvailability: routeModelAvailability(),
    stance: stance.value,
    viewHint: viewHint.value,
    debugVideo: debugVideo.value
  };
  assignOptionalString(payload, "templatePath", templatePath.value);
  assignOptionalString(payload, "previewOut", previewOut.value);
  assignOptionalString(payload, "debugVideoPath", debugVideoPath.value);

  const pendingJobId = nextBridgeId("analysis-job");
  analysisJobId.value = pendingJobId;
  const response = await sendBridgeCommand("analysis.run", payload, { jobId: pendingJobId });
  setRawJson(response);
  if (!response.ok) {
    analysisStatus.value = "动作分析失败";
    analysisJobId.value = undefined;
    errorText.value = response.error?.message ?? "动作分析失败";
    return;
  }
  analysisJobId.value = response.jobId ?? pendingJobId;
  applyBackendRouteNotice(response.payload.backendRoute);
}

async function stopAnalysisJob(): Promise<void> {
  const response = await stopJobById(sendBridgeCommand, analysisJobId.value);
  if (!response) return;
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "停止动作分析失败";
    return;
  }
  analysisStatus.value = "已停止";
  analysisJobId.value = undefined;
  analysisProgress.value = null;
}

function handleBridgeEvent(event: BridgeEnvelope): void {
  setRawJson(event);
  if (!shouldApplyBridgeEvent(event)) {
    return;
  }
  if (event.event === "session.status") {
    const state = String(event.payload.state ?? "");
    if (state === "running") {
      statusText.value = "运行中…";
      isRunning.value = true;
      const nextProgressText = progressTextForSessionStatus(event.payload);
      if (nextProgressText) {
        progressText.value = nextProgressText;
      }
      applyBackendRouteNotice(event.payload.backendRoute);
    }
    if (state === "completed" || state === "stopped") {
      statusText.value = "已停止";
      isRunning.value = false;
    }
  }
  if (event.event === "session.frame") {
    const payload = event.payload as SessionFramePayload;
    if (!acceptLatestFrameIdentity(payload, event.sessionId ?? null, event.jobId ?? null)) {
      return;
    }
    queueLatestFrame(payload, event.sessionId ?? null, event.jobId ?? null);
  }
  if (event.event === "record.status") {
    applyRecordPayload(event.payload as unknown as RecordState);
  }
  if (event.event === "template.progress" || event.event === "analysis.progress") {
    applyAnalysisProgress(event.payload);
  }
  if (event.event === "model.progress") {
    applyModelProgress(event.payload);
  }
  if (event.event === "model.status") {
    applyModelStatusPayload(event.payload);
  }
  if (event.event === "template.status" || event.event === "analysis.status") {
    applyAnalysisPayload(event.payload);
  }
  if (event.event === "job.completed" || event.event === "job.stopped" || event.event === "job.failed") {
    if (event.jobId === modelDownloadJobId.value) {
      const summary = modelDownloadStatusFromJobEvent(event);
      modelDownloadStatus.value = summary.status;
      if (summary.failed.length > 0 || event.event === "job.failed") {
        errorText.value = summary.status;
      }
      modelDownloadJobId.value = undefined;
      void refreshModels();
      return;
    }
    if (event.jobId === analysisJobId.value) {
      if (event.event === "job.failed") {
        analysisStatus.value = "失败";
        analysisJobId.value = undefined;
        if (event.error) {
          errorText.value = event.error.message;
        }
        return;
      }
      const result = isJsonRecord(event.payload.result) ? event.payload.result : event.payload;
      applyAnalysisPayload(result);
      analysisStatus.value = event.event === "job.stopped" ? "已停止" : "已完成";
      analysisJobId.value = undefined;
      return;
    }
    const sessionTerminalStatus = sessionStatusFromJobEvent(event);
    if (sessionTerminalStatus && (!event.jobId || event.jobId === jobId.value)) {
      markSessionStopped(sessionTerminalStatus, { clearSession: event.event === "job.failed" });
      if (event.event === "job.failed") {
        cancelPendingFrameRender();
        clearPreviewCanvas();
      }
    }
  }
  if (event.error) {
    errorText.value = event.error.message;
  }
}

function acceptLatestFrameIdentity(
  payload: SessionFramePayload,
  eventSessionId: string | null,
  eventJobId: string | null
): boolean {
  const frameId = Number(payload.frameId ?? 0);
  const frameHandle = typeof payload.frameHandle === "string" ? payload.frameHandle : "";
  if (!Number.isFinite(frameId) || frameId <= 0 || !frameHandle) {
    return false;
  }
  latestFrameIdentity = { sessionId: eventSessionId, jobId: eventJobId, frameId, frameHandle };
  return true;
}

function queueLatestFrame(payload: SessionFramePayload, eventSessionId: string | null, eventJobId: string | null): void {
  const frameId = Number(payload.frameId ?? 0);
  const frameHandle = typeof payload.frameHandle === "string" ? payload.frameHandle : "";
  if (!Number.isFinite(frameId) || frameId <= 0 || !frameHandle) {
    return;
  }
  pendingFrame = { payload, sessionId: eventSessionId, jobId: eventJobId, frameId, frameHandle };
  if (isRenderingFrame) {
    return;
  }
  if (frameRenderRaf == null) {
    frameRenderRaf = window.requestAnimationFrame(() => {
      frameRenderRaf = null;
      void drainLatestFrameRender();
    });
  }
}

async function drainLatestFrameRender(): Promise<void> {
  if (isRenderingFrame) {
    return;
  }
  isRenderingFrame = true;
  try {
    while (pendingFrame) {
      const next = pendingFrame;
      pendingFrame = null;
      await renderLatestFrame(next);
    }
  } finally {
    isRenderingFrame = false;
  }
  if (pendingFrame && frameRenderRaf == null) {
    frameRenderRaf = window.requestAnimationFrame(() => {
      frameRenderRaf = null;
      void drainLatestFrameRender();
    });
  }
}

async function renderLatestFrame(frame: PendingFrame): Promise<void> {
  try {
    const response = await fetchLatestFrameBytes(frame.payload);
    if (!response) return;
    const actualFrame: FrameIdentity = {
      sessionId: frame.sessionId,
      jobId: frame.jobId,
      frameId: response.frameId,
      frameHandle: frame.frameHandle
    };
    if (!isDrawableFrame(actualFrame)) {
      return;
    }
    const blob = new Blob([response.bytes], { type: "image/jpeg" });
    const bitmap = await createImageBitmap(blob);
    try {
      const canvas = previewCanvas.value;
      if (!canvas || !isDrawableFrame(actualFrame)) {
        return;
      }
      if (canvas.width !== bitmap.width) {
        canvas.width = bitmap.width;
      }
      if (canvas.height !== bitmap.height) {
        canvas.height = bitmap.height;
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0);
      lastDrawnFrameId = response.frameId;
      applyFrameMetadata(frame.payload);
    } finally {
      bitmap.close();
    }
  } catch (error) {
    const message = errorMessage(error, "读取最新预览帧失败");
    if (!message.includes("stale")) {
      errorText.value = message;
    }
  }
}

function isDrawableFrame(frame: FrameIdentity): boolean {
  if (frame.sessionId !== sessionId.value || frame.jobId !== jobId.value) {
    return false;
  }
  if (frame.frameId < lastDrawnFrameId) {
    return false;
  }
  return isCurrentFrameIdentity(frame, { sessionId: frame.sessionId, jobId: frame.jobId, frameId: lastDrawnFrameId, frameHandle: "" });
}

function applyFrameMetadata(payload: SessionFramePayload): void {
  actionsText.value = String(payload.actionsText ?? "-");
  frameIndex.value = Number(payload.frameIndex ?? 0);
  fpsText.value = Number(payload.fps ?? 0).toFixed(1);
  const nextProgressText = progressTextForFrameProgress(payload.progress);
  if (nextProgressText) {
    progressText.value = nextProgressText;
  }
  applyBackendRouteNotice(payload.backendRoute);
  applyReviewNotice(payload);
}

function applyBackendRouteNotice(routeValue: unknown): void {
  if (!isJsonRecord(routeValue)) {
    return;
  }
  const requestedBackend = String(routeValue.requestedBackend ?? routeValue.requested_backend ?? "");
  const fallbackReason = String(routeValue.fallbackReason ?? routeValue.fallback_reason ?? "");
  if (requestedBackend === "yolo" && fallbackReason) {
    fallbackNotice.value = `YOLO 预览已回退：${fallbackReason}`;
  }
}

function applyReviewNotice(payload: JsonRecord): void {
  if (payload.multiPersonDetected === true || payload.reviewRequired === true) {
    const count = Number(payload.personCount ?? 0);
    reviewNotice.value = count > 1 ? `检测到多人：${count} 人，结果需复核` : "检测到多人，结果需复核";
  }
}

function routeModelAvailability(): JsonRecord {
  const yoloModels = models.value.filter((model) => model.category === "yolo");
  const byKey = new Map(yoloModels.map((model) => [model.key, model]));
  const isRoutableYolo = (model: ModelItem | undefined) => Boolean(model?.installed && model.runtimeSupported === true);
  const yoloRuntimeSupported = yoloModels.some((model) => isRoutableYolo(model));
  const yoloRealtimeModel = isRoutableYolo(byKey.get("yolo26n"))
    ? "yolo26n"
    : isRoutableYolo(byKey.get("yolo26s")) ? "yolo26s" : "";
  const yoloRealtime = Boolean(yoloRealtimeModel);
  const yolo26L = isRoutableYolo(byKey.get("yolo26l"));
  return {
    yoloSupported: yoloRuntimeSupported,
    yoloRealtime,
    yoloRealtimeModel,
    yolo26L,
    reason: yoloRuntimeSupported ? "" : (yoloRuntimeMessage.value || "YOLO runtime unavailable")
  };
}

function setRawJson(envelope: BridgeEnvelope): void {
  rawJson.value = JSON.stringify(sanitizedRawEnvelope(envelope), null, 2);
}

function shouldApplyBridgeEvent(event: BridgeEnvelope): boolean {
  return isBridgeEventForCurrentState(event, {
    sessionId: sessionId.value,
    sessionJobId: jobId.value,
    analysisJobId: analysisJobId.value,
    modelDownloadJobId: modelDownloadJobId.value
  });
}

function cancelPendingFrameRender(): void {
  pendingFrame = null;
  latestFrameIdentity = null;
  lastDrawnFrameId = 0;
  if (frameRenderRaf != null) {
    window.cancelAnimationFrame(frameRenderRaf);
    frameRenderRaf = null;
  }
}

function markSessionStopped(nextStatus: string, options: { clearSession?: boolean } = {}): void {
  isRunning.value = false;
  statusText.value = nextStatus;
  jobId.value = undefined;
  if (options.clearSession ?? true) {
    sessionId.value = undefined;
  }
  fallbackNotice.value = "";
  reviewNotice.value = "";
  cancelPendingFrameRender();
  if (nextStatus !== "运行失败") {
    clearPreviewCanvas();
  }
}

function clearPreviewCanvas(): void {
  const canvas = previewCanvas.value;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

function applyAnalysisProgress(payload: JsonRecord): void {
  analysisProgress.value = {
    stage: String(payload.stage ?? "处理中"),
    done: Number(payload.done ?? 0),
    total: Number(payload.total ?? 0),
    percent: payload.percent == null ? null : Number(payload.percent)
  };
  analysisStatus.value = analysisProgress.value.stage;
}

function applyModelProgress(payload: JsonRecord): void {
  modelDownloadProgress.value = {
    stage: String(payload.stage ?? payload.key ?? "下载中"),
    done: Number(payload.done ?? payload.downloaded ?? 0),
    total: Number(payload.total ?? 0),
    percent: payload.percent == null ? null : Number(payload.percent)
  };
  modelDownloadStatus.value = modelDownloadProgress.value.stage;
}

function applyModelStatusPayload(payload: JsonRecord): void {
  const summary = modelDownloadStatusFromPayload(payload);
  if (!summary) {
    return;
  }
  modelDownloadStatus.value = summary.status;
  if (summary.failed.length > 0) {
    errorText.value = summary.status;
  }
}

function applyAnalysisPayload(payload: JsonRecord): void {
  analysisResult.value = payload;
  if (typeof payload.templatePath === "string" && payload.templatePath) {
    templatePath.value = payload.templatePath;
    analysisStatus.value = "模板已生成";
  }
  if (payload.compare || payload.techEval) {
    analysisStatus.value = "分析结果已更新";
  }
}

function assignOptionalString(payload: JsonRecord, key: string, value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    payload[key] = trimmed;
  }
}

function assignOptionalInt(payload: JsonRecord, key: string, value: string): void {
  const trimmed = value.trim();
  if (!trimmed) return;
  const parsed = Number.parseInt(trimmed, 10);
  if (Number.isFinite(parsed)) {
    payload[key] = parsed;
  }
}

function nextBridgeId(prefix: string): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) {
    return `${prefix}-${cryptoApi.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  const text = String(error ?? "").trim();
  return text || fallback;
}

function formatScore(value: unknown): string {
  const numberValue = Number(value ?? 0);
  if (!Number.isFinite(numberValue)) return "-";
  return numberValue.toFixed(3);
}

function formatProgress(progress: AnalysisProgress | null): string {
  if (!progress) return "-";
  if (progress.percent == null) {
    return `${progress.stage} (${progress.done}/${progress.total || "?"})`;
  }
  return `${progress.stage} (${progress.done}/${progress.total}, ${progress.percent.toFixed(1)}%)`;
}

function applyRecordPayload(payload: RecordState): void {
  recordState.value = {
    state: payload.state ?? "idle",
    buttonText: payload.buttonText ?? "开始录制",
    stopEnabled: Boolean(payload.stopEnabled),
    resultPath: payload.resultPath ?? null,
    framesWritten: Number(payload.framesWritten ?? 0),
    lastError: payload.lastError ?? null
  };
  if (recordState.value.lastError) {
    errorText.value = `录制发生错误：${recordState.value.lastError}`;
  }
}
</script>

<template>
  <main class="app-shell">
    <aside class="control-rail">
      <section class="panel">
        <div class="panel-toolbar">
          <div class="panel-title">主要操作</div>
          <button class="settings-toggle" @click="showSettingsPanel = !showSettingsPanel">⚙ 设置</button>
        </div>
        <label class="field-label" for="camera">选择摄像头：</label>
        <div class="path-row">
          <select id="camera" v-model.number="cameraIndex" :disabled="isRunning || cameras.length === 0">
            <option v-for="camera in cameras" :key="camera.index" :value="camera.index">
              {{ camera.label }}
            </option>
          </select>
          <button class="secondary-button" :disabled="isRunning" @click="refreshCameras">刷新</button>
        </div>

        <label class="field-label" for="model">人体姿态模型：</label>
        <select id="model" v-model="poseVariant" :disabled="isRunning" @change="refreshModels">
          <option value="lite">lite</option>
          <option value="full">full</option>
          <option value="heavy">heavy</option>
        </select>
        <div class="button-row">
          <button class="primary-button" :disabled="!canStart" @click="startSession">开始</button>
          <button class="secondary-button" :disabled="!isRunning" @click="stopSession">停止</button>
        </div>

        <div class="subgroup">
          <div class="subgroup-title">录制</div>
          <button class="secondary-button" :disabled="!isRunning" @click="toggleRecord">
            {{ recordState.buttonText }}
          </button>
          <button class="secondary-button" :disabled="!recordState.stopEnabled" @click="stopRecord">结束录制</button>
          <label class="field-label" for="record-dir">保存目录：</label>
          <div class="path-row">
            <input id="record-dir" v-model="recordDir" :disabled="isRunning" :placeholder="defaultRecordDir" />
            <button class="secondary-button" :disabled="isRunning" @click="selectRecordDir">选择…</button>
          </div>
          <p class="hint-text">留空时使用默认输出目录：{{ defaultRecordDir }}</p>
          <p v-if="recordState.resultPath" class="hint-text">保存：{{ recordState.resultPath }}</p>
        </div>

        <button class="analysis-button" @click="showAnalysisPanel = !showAnalysisPanel">动作分析…</button>
      </section>

      <section class="panel">
        <div class="panel-title">次要选项</div>
        <p class="hint-text">{{ sourceHint }}</p>
        <label class="field-label" for="workers">线程数（&gt;1：多核并行，关闭时序平滑）：</label>
        <input id="workers" v-model.number="workers" :disabled="isRunning" min="1" type="number" />
        <label class="check-row">
          <input v-model="enableHands" :disabled="isRunning" type="checkbox" @change="refreshModels" />
          启用手部检测（V 手势 / 手部骨架）
        </label>
      </section>

      <section v-if="showAnalysisPanel" class="panel analysis-panel">
        <div class="panel-title">动作分析</div>
        <div class="subgroup">
          <div class="subgroup-title">实时输入源</div>
          <label class="field-label" for="source-kind">输入源类型</label>
          <select id="source-kind" v-model="sourceKind" :disabled="isRunning">
            <option value="camera">摄像头</option>
            <option value="video">视频文件</option>
          </select>
          <template v-if="sourceKind === 'video'">
            <label class="field-label" for="video-path">视频路径</label>
            <input id="video-path" v-model="videoPath" :disabled="isRunning" placeholder="C:\\videos\\student.mp4" />
          </template>
        </div>
        <label class="field-label" for="base-video">基准视频</label>
        <input id="base-video" v-model="baseVideo" placeholder="C:\\videos\\teacher.mp4" />
        <label class="field-label" for="template-path">已有模板路径</label>
        <input id="template-path" v-model="templatePath" placeholder="C:\\templates\\pose.npz" />
        <label class="field-label" for="template-out">模板生成输出</label>
        <input id="template-out" v-model="templateOut" placeholder="留空则使用默认模板路径" />
        <label class="field-label" for="target-video">目标视频</label>
        <input id="target-video" v-model="targetVideo" placeholder="C:\\videos\\student.mp4" />

        <div class="compact-grid">
          <label>
            <span class="field-label">startFrame</span>
            <input v-model="analysisStartFrame" inputmode="numeric" placeholder="起始帧" />
          </label>
          <label>
            <span class="field-label">endFrame</span>
            <input v-model="analysisEndFrame" inputmode="numeric" placeholder="结束帧" />
          </label>
          <label>
            <span class="field-label">worker</span>
            <input v-model.number="analysisWorkers" min="1" type="number" />
          </label>
          <label>
            <span class="field-label">previewOut</span>
            <input v-model="previewOut" placeholder="匹配预览输出" />
          </label>
        </div>

        <label class="check-row">
          <input v-model="doCompare" type="checkbox" />
          模板比对
        </label>
        <label class="check-row">
          <input v-model="doTechEval" type="checkbox" />
          启用直拳技术评估
        </label>
        <label class="check-row">
          <input v-model="highQualityBodyOnly" type="checkbox" />
          高质量 body-only 分析
        </label>
        <div class="compact-grid">
          <label>
            <span class="field-label">stance</span>
            <select v-model="stance">
              <option value="left">left</option>
              <option value="right">right</option>
            </select>
          </label>
          <label>
            <span class="field-label">viewHint</span>
            <select v-model="viewHint">
              <option value="auto">auto</option>
              <option value="front">front</option>
              <option value="side">side</option>
              <option value="mixed">mixed</option>
            </select>
          </label>
        </div>
        <label class="check-row">
          <input v-model="debugVideo" type="checkbox" />
          导出 debugVideo
        </label>
        <label class="field-label" for="debug-video-path">debugVideo 输出</label>
        <input id="debug-video-path" v-model="debugVideoPath" placeholder="留空则使用默认调试视频路径" />

        <div class="button-row">
          <button class="secondary-button" @click="createTemplate">生成模板</button>
          <button class="primary-button" @click="runAnalysis">运行分析</button>
        </div>
        <button class="secondary-button" :disabled="!analysisJobId" @click="stopAnalysisJob">停止动作分析</button>

        <p class="hint-text">状态：{{ analysisStatus }} · {{ formatProgress(analysisProgress) }}</p>
        <div v-if="compareResult" class="result-block">
          <p class="hint-text">匹配分数：{{ formatScore(compareResult.score) }}</p>
          <p class="hint-text">匹配片段：{{ compareResult.matchText ?? `${compareResult.startFrame}..${compareResult.endFrame}` }}</p>
          <p class="hint-text">预览导出：{{ compareResult.previewPath ?? "-" }}</p>
        </div>
        <div v-if="techEvalResult" class="result-block">
          <p class="hint-text">技术评估视角：{{ techEvalResult.viewMode ?? "-" }}</p>
          <p class="hint-text">debugVideo：{{ techEvalResult.debugVideo ?? "-" }}</p>
          <div v-for="row in techIndicatorRows" :key="row.key" class="indicator-row">
            <strong>{{ row.label }}：{{ row.status }}</strong>
            <span>{{ row.reason }}</span>
            <span>原因类型：{{ row.primaryCause }} / 失败环节：{{ row.failedStage }}</span>
          </div>
        </div>
      </section>
    </aside>

    <section class="preview-stage">
      <div class="stage-header">
        <div>
          <p class="eyebrow">{{ sourceHint }}</p>
          <h2>实时预览</h2>
        </div>
        <div class="status-pill" :class="{ running: isRunning }">{{ statusText }}</div>
      </div>
      <div class="video-frame">
        <canvas ref="previewCanvas" aria-label="实时识别预览帧"></canvas>
        <div v-if="!isRunning && frameIndex === 0" class="skeleton-grid">
          <span v-for="n in 22" :key="n"></span>
        </div>
        <div class="frame-overlay">
          {{ isRunning ? `Frame ${frameIndex}` : "等待开始识别" }}
        </div>
      </div>
      <div v-if="fallbackNotice" class="warning-strip">{{ fallbackNotice }}</div>
      <div v-if="reviewNotice" class="warning-strip">{{ reviewNotice }}</div>
      <div class="status-grid">
        <div>
          <span class="metric-label">识别结果</span>
          <strong>{{ actionsText }}</strong>
        </div>
        <div>
          <span class="metric-label">进度</span>
          <strong>{{ progressText }}</strong>
        </div>
      </div>
      <div v-if="errorText" class="error-strip">{{ errorText }}</div>
    </section>

    <div v-if="showSettingsPanel" class="modal-overlay" @click.self="showSettingsPanel = false">
      <div class="modal-dialog" role="dialog" aria-label="设置">
        <div class="modal-header">
          <div class="modal-title">设置</div>
          <button class="modal-close" aria-label="关闭" @click="showSettingsPanel = false">×</button>
        </div>
        <div class="modal-body">
          <div class="subgroup">
            <div class="subgroup-title">当前模型</div>
            <p class="settings-text">姿态模型：{{ poseVariant }}　手部检测：{{ enableHands ? "开启" : "关闭" }}</p>
            <p v-if="activeModels.length === 0" class="settings-text">模型状态未刷新</p>
            <p v-for="model in activeModels" :key="model.key" class="settings-text">
              {{ model.label }}（{{ model.installed ? "已就绪" : "缺失" }}）
            </p>
            <p v-if="missingActiveModels.length" class="error-text">⚠ 缺失模型会导致无法开始识别，请在下方下载后再使用。</p>
          </div>

          <div class="subgroup">
            <div class="subgroup-title">模型管理</div>
            <p class="settings-text">模型目录：{{ modelsDir || "-" }}</p>
            <p v-if="yoloRuntimeMessage" class="settings-text">{{ yoloRuntimeMessage }}</p>
            <div v-for="model in models" :key="model.key" class="model-row">
              <div class="model-main">
                <span class="model-name">{{ model.label }}</span>
                <span class="model-state">{{ model.active ? "● 使用中 " : "" }}{{ model.installed ? (model.sizeMb ? `已安装 (${model.sizeMb} MB)` : "已安装") : (model.sizeMb ? `未安装 约 ${model.sizeMb} MB` : "未安装") }}</span>
                <button class="secondary-button model-btn" :disabled="Boolean(modelDownloadJobId) || model.downloadable === false" @click="downloadModel(model.key)">
                  {{ model.downloadable === false ? "手动安装" : (model.installed ? "重新下载" : "下载") }}
                </button>
              </div>
              <div class="model-meta">
                <span>{{ model.key }} · {{ model.category ?? "mediapipe" }} · {{ model.defaultRouteEligible === false ? "不进默认路由" : "可进默认路由" }}</span>
                <span v-if="model.license">许可：{{ model.license }}</span>
                <span v-if="model.offlineInstall">离线安装：{{ model.offlineInstall }}</span>
                <span v-if="model.downloadHint">下载提示：{{ model.downloadHint }}</span>
                <span v-if="model.note">{{ model.note }}</span>
              </div>
            </div>
            <div class="button-row">
              <button class="primary-button" :disabled="missingModelKeys.length === 0 || Boolean(modelDownloadJobId)" @click="downloadAllMissing">
                下载全部缺失模型
              </button>
              <button class="secondary-button" @click="refreshModels">刷新状态</button>
            </div>
            <button class="secondary-button" :disabled="!modelDownloadJobId" @click="cancelModelDownload">
              取消下载
            </button>
          </div>

          <div class="subgroup">
            <div class="subgroup-title">状态</div>
            <p class="settings-text">{{ modelDownloadStatus }}</p>
            <progress class="settings-progress" :value="modelDownloadProgress?.percent ?? 0" max="100"></progress>
            <p class="settings-text">{{ formatProgress(modelDownloadProgress) }}</p>
            <p class="settings-note">说明：模型从 Google 官方源下载。若长时间无进度或失败，通常是网络无法访问 storage.googleapis.com，请自行配置代理后重试。</p>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>
