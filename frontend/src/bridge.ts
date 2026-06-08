import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type JsonRecord = Record<string, JsonValue>;

export type BridgeError = {
  code: string;
  message: string;
  detail: JsonRecord;
};

export type BridgeEnvelope<TPayload extends JsonRecord = JsonRecord> = {
  type: "response" | "event";
  requestId?: string;
  event?: string;
  ok?: boolean;
  jobId?: string;
  sessionId?: string;
  payload: TPayload;
  error: BridgeError | null;
  timestamp: string;
};

export type BridgeCommandRequest = {
  type: "command";
  command: string;
  requestId: string;
  jobId?: string;
  sessionId?: string;
  payload: JsonRecord;
};

export type CameraEntry = {
  label: string;
  index: number;
};

export type RecordState = {
  state: "idle" | "recording" | "paused";
  buttonText: string;
  stopEnabled: boolean;
  resultPath: string | null;
  framesWritten: number;
  lastError: string | null;
};

const mockListeners = new Set<(event: BridgeEnvelope) => void>();

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function sendBridgeCommand<TPayload extends JsonRecord = JsonRecord>(
  command: string,
  payload: JsonRecord = {},
  options: { jobId?: string; sessionId?: string } = {}
): Promise<BridgeEnvelope<TPayload>> {
  const request: BridgeCommandRequest = {
    type: "command",
    command,
    requestId: nextRequestId(),
    jobId: options.jobId,
    sessionId: options.sessionId,
    payload
  };
  if (!isTauriRuntime()) {
    return mockBridgeCommand<TPayload>(request);
  }
  return invoke<BridgeEnvelope<TPayload>>("bridge_command", { request });
}

export async function listenBridgeEvents(callback: (event: BridgeEnvelope) => void): Promise<UnlistenFn> {
  if (!isTauriRuntime()) {
    mockListeners.add(callback);
    return () => mockListeners.delete(callback);
  }
  return listen<BridgeEnvelope>("bridge-event", (event) => callback(event.payload));
}

function nextRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && "randomUUID" in cryptoApi) {
    return cryptoApi.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function mockEvent(event: BridgeEnvelope): void {
  for (const listener of mockListeners) {
    listener(event);
  }
}

async function mockBridgeCommand<TPayload extends JsonRecord>(
  request: BridgeCommandRequest
): Promise<BridgeEnvelope<TPayload>> {
  const base = {
    type: "response" as const,
    requestId: request.requestId,
    ok: true,
    jobId: request.jobId,
    sessionId: request.sessionId,
    error: null,
    timestamp: new Date().toISOString()
  };

  if (request.command === "camera.list") {
    return {
      ...base,
      payload: {
        cameras: [
          { label: "摄像头 0", index: 0 },
          { label: "摄像头 1: USB Camera", index: 1 }
        ],
        count: 2,
        scanLimit: request.payload.scanLimit ?? 5
      } as unknown as TPayload
    };
  }

  if (request.command === "model.status") {
    return {
      ...base,
      payload: {
        modelsDir: "models",
        activeKeys: ["hand", "pose_full"],
        missingKeys: [],
        models: [
          { key: "pose_full", label: "人体姿态 - full（默认，均衡）", installed: true, active: true, sizeMb: 9 },
          { key: "hand", label: "手部关键点 - hand_landmarker", installed: true, active: true, sizeMb: 7.5 }
        ]
      } as unknown as TPayload
    };
  }

  if (request.command === "session.start") {
    const sessionId = request.sessionId ?? nextRequestId();
    const jobId = request.jobId ?? nextRequestId();
    window.setTimeout(() => {
      mockEvent({
        type: "event",
        event: "session.status",
        jobId,
        sessionId,
        payload: { state: "running", totalFrames: 0 },
        error: null,
        timestamp: new Date().toISOString()
      });
      mockEvent({
        type: "event",
        event: "session.frame",
        jobId,
        sessionId,
        payload: {
          image: "",
          actions: ["HANDS_UP"],
          actionsZh: ["双手举起"],
          actionsText: "双手举起",
          frameIndex: 1,
          fps: 30,
          progress: { done: 1, total: 0, percent: null },
          size: { width: 1280, height: 720 }
        },
        error: null,
        timestamp: new Date().toISOString()
      });
    }, 250);
    return {
      ...base,
      jobId,
      sessionId,
      payload: { state: "starting", jobId, sessionId } as unknown as TPayload
    };
  }

  if (request.command === "session.stop") {
    return { ...base, payload: { stopped: true, jobIds: [request.jobId ?? "mock-job"] } as unknown as TPayload };
  }

  if (request.command === "record.toggle") {
    return {
      ...base,
      payload: {
        state: "recording",
        buttonText: "暂停录制",
        stopEnabled: true,
        resultPath: null,
        framesWritten: 0,
        lastError: null
      } as unknown as TPayload
    };
  }

  if (request.command === "record.stop") {
    return {
      ...base,
      payload: {
        state: "idle",
        buttonText: "开始录制",
        stopEnabled: false,
        resultPath: "outputs/record_mock.mp4",
        framesWritten: 0,
        lastError: null
      } as unknown as TPayload
    };
  }

  return { ...base, payload: {} as TPayload };
}
