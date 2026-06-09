<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  type BridgeEnvelope,
  type CameraEntry,
  type JsonRecord,
  type RecordState,
  listenBridgeEvents,
  selectDirectory,
  sendBridgeCommand
} from "./bridge";
import {
  initialSessionProgressText,
  isBridgeEventForCurrentState,
  modelDownloadStatusFromJobEvent,
  modelDownloadStatusFromPayload,
  progressTextForFrameProgress,
  progressTextForSessionStatus
} from "./bridge-state";

type SourceKind = "none" | "camera" | "video";

type ModelItem = {
  key: string;
  label: string;
  installed: boolean;
  active: boolean;
  path?: string;
  sizeMb?: number | null;
};

type SessionFramePayload = JsonRecord & {
  image?: string;
  actionsText?: string;
  fps?: number;
  frameIndex?: number;
  progress?: { done: number; total: number; percent: number | null };
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
const sourceKind = ref<SourceKind>("none");
const videoPath = ref("");
const poseVariant = ref<"lite" | "full" | "heavy">("full");
const workers = ref(1);
const enableHands = ref(true);
const recordDir = ref("");
const defaultRecordDir = "Python outputs_dir()";

const statusText = ref("就绪");
const actionsText = ref("-");
const fpsText = ref("--");
const progressText = ref("等待开始");
const previewImage = ref("");
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

const modelSummary = computed(() => {
  if (models.value.length === 0) return "模型状态未刷新";
  const active = models.value.filter((model) => model.active);
  const missing = active.filter((model) => !model.installed);
  if (missing.length === 0) {
    return active.map((model) => `${model.label} 已就绪`).join(" / ");
  }
  return `缺失：${missing.map((model) => model.label).join(" / ")}`;
});

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
let lastPreviewFrameAt = 0;
const PREVIEW_FRAME_MIN_INTERVAL_MS = 100;

onMounted(async () => {
  unlisten = await listenBridgeEvents(handleBridgeEvent);
  await Promise.all([refreshCameras(), refreshModels()]);
});

onBeforeUnmount(() => {
  if (unlisten) unlisten();
  if (isRunning.value) {
    void stopSession();
  }
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
  const payload = response.payload as unknown as { modelsDir: string; models: ModelItem[]; missingKeys: string[] };
  modelsDir.value = payload.modelsDir ?? "";
  models.value = payload.models ?? [];
  missingModelKeys.value = payload.missingKeys ?? [];
}

async function downloadModel(modelKey: string): Promise<void> {
  const response = await sendBridgeCommand("model.download", { modelKey });
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "模型下载失败";
    return;
  }
  modelDownloadJobId.value = response.jobId;
  modelDownloadStatus.value = `下载中：${modelKey}`;
  modelDownloadProgress.value = null;
}

async function downloadAllMissing(): Promise<void> {
  const response = await sendBridgeCommand("model.download", { allMissing: true });
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "下载缺失模型失败";
    return;
  }
  modelDownloadJobId.value = response.jobId;
  modelDownloadStatus.value = "下载全部缺失模型中";
  modelDownloadProgress.value = null;
}

async function cancelModelDownload(): Promise<void> {
  if (!modelDownloadJobId.value) return;
  const response = await sendBridgeCommand("job.stop", { jobId: modelDownloadJobId.value }, { jobId: modelDownloadJobId.value });
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "取消模型下载失败";
  }
}

async function startSession(): Promise<void> {
  if (!canStart.value) return;
  errorText.value = "";
  statusText.value = "启动中…";
  actionsText.value = "-";
  fpsText.value = "--";
  progressText.value = initialSessionProgressText();
  previewImage.value = "";
  const payload: JsonRecord = {
    sourceKind: sourceKind.value,
    poseVariant: poseVariant.value,
    workers: workers.value,
    enableHands: enableHands.value
  };
  assignOptionalString(payload, "recordDir", recordDir.value);
  if (sourceKind.value === "camera") {
    payload.cameraIndex = cameraIndex.value;
  } else {
    payload.videoPath = videoPath.value.trim();
  }
  const response = await sendBridgeCommand("session.start", payload);
  setRawJson(response);
  if (!response.ok) {
    statusText.value = "启动失败";
    errorText.value = response.error?.message ?? "启动失败";
    return;
  }
  isRunning.value = true;
  sessionId.value = response.sessionId;
  jobId.value = response.jobId;
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
  }
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

  const response = await sendBridgeCommand("template.create", payload);
  setRawJson(response);
  if (!response.ok) {
    analysisStatus.value = "模板生成失败";
    errorText.value = response.error?.message ?? "模板生成失败";
    return;
  }
  analysisJobId.value = response.jobId;
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
  if (!doCompare.value && !doTechEval.value) {
    errorText.value = "请至少启用模板比对或直拳技术评估";
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
    stance: stance.value,
    viewHint: viewHint.value,
    debugVideo: debugVideo.value
  };
  assignOptionalString(payload, "templatePath", templatePath.value);
  assignOptionalString(payload, "previewOut", previewOut.value);
  assignOptionalString(payload, "debugVideoPath", debugVideoPath.value);

  const response = await sendBridgeCommand("analysis.run", payload);
  setRawJson(response);
  if (!response.ok) {
    analysisStatus.value = "动作分析失败";
    errorText.value = response.error?.message ?? "动作分析失败";
    return;
  }
  analysisJobId.value = response.jobId;
}

async function stopAnalysisJob(): Promise<void> {
  if (!analysisJobId.value) return;
  const response = await sendBridgeCommand("job.stop", { jobId: analysisJobId.value }, { jobId: analysisJobId.value });
  setRawJson(response);
  if (!response.ok) {
    errorText.value = response.error?.message ?? "停止动作分析失败";
  }
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
    }
    if (state === "completed" || state === "stopped") {
      statusText.value = "已停止";
      isRunning.value = false;
    }
  }
  if (event.event === "session.frame") {
    if (!shouldRenderPreviewFrame()) {
      return;
    }
    const payload = event.payload as SessionFramePayload;
    previewImage.value = String(payload.image ?? "");
    actionsText.value = String(payload.actionsText ?? "-");
    frameIndex.value = Number(payload.frameIndex ?? 0);
    fpsText.value = Number(payload.fps ?? 0).toFixed(1);
    const nextProgressText = progressTextForFrameProgress(payload.progress);
    if (nextProgressText) {
      progressText.value = nextProgressText;
    }
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
  if (event.event === "job.completed" || event.event === "job.stopped") {
    if (event.jobId === modelDownloadJobId.value) {
      const summary = modelDownloadStatusFromJobEvent(event);
      modelDownloadStatus.value = summary.status;
      if (summary.failed.length > 0) {
        errorText.value = summary.status;
      }
      modelDownloadJobId.value = undefined;
      void refreshModels();
      return;
    }
    if (event.jobId === analysisJobId.value) {
      const result = isJsonRecord(event.payload.result) ? event.payload.result : event.payload;
      applyAnalysisPayload(result);
      analysisStatus.value = event.event === "job.stopped" ? "已停止" : "已完成";
      analysisJobId.value = undefined;
      return;
    }
    if (!event.jobId || event.jobId === jobId.value) {
      isRunning.value = false;
      statusText.value = "已停止";
    }
  }
  if (event.error) {
    errorText.value = event.error.message;
  }
}

function setRawJson(envelope: BridgeEnvelope): void {
  rawJson.value = JSON.stringify(envelope, null, 2);
}

function shouldApplyBridgeEvent(event: BridgeEnvelope): boolean {
  return isBridgeEventForCurrentState(event, {
    sessionId: sessionId.value,
    sessionJobId: jobId.value,
    analysisJobId: analysisJobId.value,
    modelDownloadJobId: modelDownloadJobId.value
  });
}

function shouldRenderPreviewFrame(): boolean {
  const now = Date.now();
  if (now - lastPreviewFrameAt < PREVIEW_FRAME_MIN_INTERVAL_MS) {
    return false;
  }
  lastPreviewFrameAt = now;
  return true;
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

function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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
      <section class="brand-block">
        <div class="brand-mark">V</div>
        <div>
          <h1>Vision 动作识别与评分</h1>
          <p>Vue + Tauri 桌面前端</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">输入源</div>
        <div class="segmented">
          <button :class="{ active: sourceKind === 'none' }" :disabled="isRunning" @click="sourceKind = 'none'">
            未选择
          </button>
          <button :class="{ active: sourceKind === 'camera' }" :disabled="isRunning" @click="sourceKind = 'camera'">
            摄像头
          </button>
          <button :class="{ active: sourceKind === 'video' }" :disabled="isRunning" @click="sourceKind = 'video'">
            视频文件
          </button>
        </div>
        <template v-if="sourceKind === 'camera'">
          <div class="button-row">
            <button class="secondary-button" :disabled="isRunning" @click="refreshCameras">刷新摄像头</button>
            <button class="secondary-button" :disabled="isRunning || cameras.length === 0" @click="refreshModels">
              刷新模型
            </button>
          </div>
          <label class="field-label" for="camera">选择摄像头</label>
          <select id="camera" v-model.number="cameraIndex" :disabled="isRunning || cameras.length === 0">
            <option v-for="camera in cameras" :key="camera.index" :value="camera.index">
              {{ camera.label }}
            </option>
          </select>
        </template>
        <template v-else-if="sourceKind === 'video'">
          <label class="field-label" for="video-path">视频路径</label>
          <input id="video-path" v-model="videoPath" :disabled="isRunning" placeholder="C:\\videos\\student.mp4" />
        </template>
        <p v-else class="hint-text">请选择摄像头或视频文件后开始识别。</p>

        <label class="field-label" for="model">人体姿态模型</label>
        <select id="model" v-model="poseVariant" :disabled="isRunning" @change="refreshModels">
          <option value="lite">lite</option>
          <option value="full">full</option>
          <option value="heavy">heavy</option>
        </select>
        <div class="button-row">
          <button class="primary-button" :disabled="!canStart" @click="startSession">开始</button>
          <button class="secondary-button" :disabled="!isRunning" @click="stopSession">停止</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">录制</div>
        <button class="secondary-button" :disabled="!isRunning" @click="toggleRecord">
          {{ recordState.buttonText }}
        </button>
        <button class="secondary-button" :disabled="!recordState.stopEnabled" @click="stopRecord">结束录制</button>
        <label class="field-label" for="record-dir">保存目录</label>
        <div class="path-row">
          <input id="record-dir" v-model="recordDir" :disabled="isRunning" :placeholder="defaultRecordDir" />
          <button class="secondary-button" :disabled="isRunning" @click="selectRecordDir">选择目录</button>
        </div>
        <p class="hint-text">留空时使用默认输出目录：{{ defaultRecordDir }}</p>
        <p v-if="recordState.resultPath" class="hint-text">保存：{{ recordState.resultPath }}</p>
      </section>

      <section class="panel">
        <div class="panel-title">次要选项</div>
        <label class="field-label" for="workers">线程数</label>
        <input id="workers" v-model.number="workers" :disabled="isRunning" min="1" type="number" />
        <label class="check-row">
          <input v-model="enableHands" :disabled="isRunning" type="checkbox" @change="refreshModels" />
          启用手部检测
        </label>
        <button class="analysis-button" @click="showAnalysisPanel = !showAnalysisPanel">动作分析…</button>
      </section>

      <section v-if="showAnalysisPanel" class="panel analysis-panel">
        <div class="panel-title">动作分析</div>
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

      <section class="panel">
        <div class="panel-title">模型状态</div>
        <p class="hint-text">{{ modelSummary }}</p>
        <p v-if="missingModelKeys.length" class="error-text">缺失模型：{{ missingModelKeys.join(", ") }}</p>
        <button class="secondary-button" @click="showSettingsPanel = !showSettingsPanel">设置</button>
        <div v-if="showSettingsPanel" class="settings-panel">
          <p class="hint-text">模型目录：{{ modelsDir || "-" }}</p>
          <div class="button-row">
            <button class="secondary-button" @click="refreshModels">刷新状态</button>
            <button class="primary-button" :disabled="missingModelKeys.length === 0 || Boolean(modelDownloadJobId)" @click="downloadAllMissing">
              下载全部缺失
            </button>
          </div>
          <button class="secondary-button" :disabled="!modelDownloadJobId" @click="cancelModelDownload">
            取消下载
          </button>
          <p class="hint-text">下载状态：{{ modelDownloadStatus }} · {{ formatProgress(modelDownloadProgress) }}</p>
          <div v-for="model in models" :key="model.key" class="model-row">
            <div>
              <strong>{{ model.label }}</strong>
              <span>{{ model.key }} · {{ model.installed ? "已安装" : "缺失" }} · {{ model.active ? "当前启用" : "未启用" }}</span>
              <span>大小：{{ model.sizeMb ?? "-" }} MB</span>
              <span>path：{{ model.path ?? "-" }}</span>
            </div>
            <button class="secondary-button" :disabled="model.installed || Boolean(modelDownloadJobId)" @click="downloadModel(model.key)">
              下载
            </button>
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
        <img v-if="previewImage" :src="previewImage" alt="实时识别预览帧" />
        <div v-else class="skeleton-grid">
          <span v-for="n in 22" :key="n"></span>
        </div>
        <div class="frame-overlay">
          {{ isRunning ? `Frame ${frameIndex}` : "等待开始识别" }}
        </div>
      </div>
      <div class="status-grid">
        <div>
          <span class="metric-label">识别结果</span>
          <strong>{{ actionsText }}</strong>
        </div>
        <div>
          <span class="metric-label">FPS</span>
          <strong>{{ fpsText }}</strong>
        </div>
        <div>
          <span class="metric-label">进度</span>
          <strong>{{ progressText }}</strong>
        </div>
      </div>
      <div v-if="errorText" class="error-strip">{{ errorText }}</div>
      <details class="raw-panel">
        <summary>Raw JSON</summary>
        <pre>{{ rawJson }}</pre>
      </details>
    </section>
  </main>
</template>
