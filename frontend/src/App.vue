<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  type BridgeEnvelope,
  type CameraEntry,
  type JsonRecord,
  type RecordState,
  listenBridgeEvents,
  sendBridgeCommand
} from "./bridge";

type SourceKind = "camera" | "video";

type ModelItem = {
  key: string;
  label: string;
  installed: boolean;
  active: boolean;
  sizeMb?: number | null;
};

type SessionFramePayload = JsonRecord & {
  image?: string;
  actionsText?: string;
  fps?: number;
  frameIndex?: number;
  progress?: { done: number; total: number; percent: number | null };
};

const cameras = ref<CameraEntry[]>([]);
const cameraIndex = ref<number>(0);
const sourceKind = ref<SourceKind>("camera");
const videoPath = ref("");
const poseVariant = ref<"lite" | "full" | "heavy">("full");
const workers = ref(1);
const enableHands = ref(true);
const recordDir = ref("outputs");

const statusText = ref("就绪");
const actionsText = ref("-");
const fpsText = ref("--");
const progressText = ref("0%");
const previewImage = ref("");
const frameIndex = ref(0);
const isRunning = ref(false);
const sessionId = ref<string | undefined>();
const jobId = ref<string | undefined>();
const errorText = ref("");
const rawJson = ref("{}");

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

const sourceHint = computed(() => {
  if (sourceKind.value === "camera") {
    return `当前输入源：摄像头 ${cameraIndex.value}`;
  }
  return videoPath.value ? `当前输入源：视频文件 ${videoPath.value}` : "当前输入源：未选择视频文件";
});

const canStart = computed(() => {
  if (isRunning.value) return false;
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

let unlisten: (() => void) | undefined;

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
  if (!response.ok) {
    errorText.value = response.error?.message ?? "刷新模型状态失败";
    return;
  }
  const payload = response.payload as unknown as { models: ModelItem[]; missingKeys: string[] };
  models.value = payload.models ?? [];
  missingModelKeys.value = payload.missingKeys ?? [];
}

async function startSession(): Promise<void> {
  if (!canStart.value) return;
  errorText.value = "";
  statusText.value = "启动中…";
  actionsText.value = "-";
  fpsText.value = "--";
  progressText.value = "0%";
  previewImage.value = "";
  const payload: JsonRecord = {
    sourceKind: sourceKind.value,
    poseVariant: poseVariant.value,
    workers: workers.value,
    enableHands: enableHands.value,
    recordDir: recordDir.value
  };
  if (sourceKind.value === "camera") {
    payload.cameraIndex = cameraIndex.value;
  } else {
    payload.videoPath = videoPath.value.trim();
  }
  const response = await sendBridgeCommand("session.start", payload);
  if (!response.ok) {
    statusText.value = "启动失败";
    errorText.value = response.error?.message ?? "启动失败";
    return;
  }
  isRunning.value = true;
  sessionId.value = response.sessionId;
  jobId.value = response.jobId;
  rawJson.value = JSON.stringify(response.payload, null, 2);
}

async function stopSession(): Promise<void> {
  if (!sessionId.value && !jobId.value) return;
  statusText.value = "正在停止…";
  await sendBridgeCommand("session.stop", { sessionId: sessionId.value ?? "", jobId: jobId.value ?? "" }, {
    sessionId: sessionId.value,
    jobId: jobId.value
  });
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

function handleBridgeEvent(event: BridgeEnvelope): void {
  rawJson.value = JSON.stringify(event.payload, null, 2);
  if (event.event === "session.status") {
    const state = String(event.payload.state ?? "");
    if (state === "running") {
      statusText.value = "运行中…";
      isRunning.value = true;
    }
    if (state === "completed" || state === "stopped") {
      statusText.value = "已停止";
      isRunning.value = false;
    }
  }
  if (event.event === "session.frame") {
    const payload = event.payload as SessionFramePayload;
    previewImage.value = String(payload.image ?? "");
    actionsText.value = String(payload.actionsText ?? "-");
    frameIndex.value = Number(payload.frameIndex ?? 0);
    fpsText.value = Number(payload.fps ?? 0).toFixed(1);
    if (payload.progress?.percent != null) {
      progressText.value = `${payload.progress.done}/${payload.progress.total} (${payload.progress.percent.toFixed(1)}%)`;
    }
  }
  if (event.event === "record.status") {
    applyRecordPayload(event.payload as unknown as RecordState);
  }
  if (event.event === "job.completed" || event.event === "job.stopped") {
    isRunning.value = false;
    statusText.value = "已停止";
  }
  if (event.error) {
    errorText.value = event.error.message;
  }
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
        <template v-else>
          <label class="field-label" for="video-path">视频路径</label>
          <input id="video-path" v-model="videoPath" :disabled="isRunning" placeholder="C:\\videos\\student.mp4" />
        </template>

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
        <input id="record-dir" v-model="recordDir" :disabled="isRunning" />
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
        <button class="analysis-button">动作分析…</button>
      </section>

      <section class="panel">
        <div class="panel-title">模型状态</div>
        <p class="hint-text">{{ modelSummary }}</p>
        <p v-if="missingModelKeys.length" class="error-text">缺失模型：{{ missingModelKeys.join(", ") }}</p>
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
