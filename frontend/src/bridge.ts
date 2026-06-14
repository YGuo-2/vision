import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { bridgeCommandFailureResponse } from "./bridge-state";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type JsonRecord = Record<string, JsonValue>;

export type BridgeError = {
  code: string;
  message: string;
  detail: JsonRecord;
};

export type BridgeEnvelope<TPayload extends JsonRecord = JsonRecord> = {
  type: "response" | "event";
  requestId?: string | null;
  event?: string | null;
  ok?: boolean | null;
  jobId?: string | null;
  sessionId?: string | null;
  payload: TPayload;
  error: BridgeError | null;
  timestamp: string;
};

export type BridgeCommandRequest = {
  type: "command";
  command: string;
  requestId: string;
  jobId?: string | null;
  sessionId?: string | null;
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

export type LatestFrameBytes = {
  frameId: number;
  bytes: ArrayBuffer;
};

const mockListeners = new Set<(event: BridgeEnvelope) => void>();

export function isTauriRuntime(): boolean {
  return isTauri();
}

export async function sendBridgeCommand<TPayload extends JsonRecord = JsonRecord>(
  command: string,
  payload: JsonRecord = {},
  options: { jobId?: string | null; sessionId?: string | null } = {}
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
  try {
    return await invoke<BridgeEnvelope<TPayload>>("bridge_command", { request });
  } catch (error) {
    return bridgeCommandFailureResponse<TPayload>(request, error);
  }
}

export async function listenBridgeEvents(callback: (event: BridgeEnvelope) => void): Promise<UnlistenFn> {
  if (!isTauriRuntime()) {
    mockListeners.add(callback);
    return () => mockListeners.delete(callback);
  }
  return listen<BridgeEnvelope>("bridge-event", (event) => callback(event.payload));
}

export async function selectDirectory(): Promise<string | null> {
  if (!isTauriRuntime()) {
    return null;
  }
  return invoke<string | null>("select_directory");
}

export async function fetchLatestFrameBytes(payload: JsonRecord): Promise<LatestFrameBytes | null> {
  const sessionId = typeof payload.sessionId === "string" ? payload.sessionId : "";
  const frameToken = typeof payload.frameToken === "string" ? payload.frameToken : "";
  const frameHandle = typeof payload.frameHandle === "string" ? payload.frameHandle : "";
  const frameId = Number(payload.frameId ?? 0);
  if (!sessionId || !frameToken || !frameHandle || !Number.isFinite(frameId) || frameId <= 0) {
    return null;
  }
  if (!isTauriRuntime()) {
    return { frameId, bytes: new ArrayBuffer(0) };
  }
  const response = await invoke<ArrayBuffer>("latest_frame", {
    request: {
      sessionId,
      frameToken,
      frameId,
      frameHandle
    }
  });
  if (response.byteLength < 8) {
    return null;
  }
  const view = new DataView(response, 0, 8);
  const actualFrameId = view.getUint32(0, false) * 2 ** 32 + view.getUint32(4, false);
  return {
    frameId: actualFrameId,
    bytes: response.slice(8)
  };
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
          sessionId,
          framePort: 0,
          frameToken: "mock",
          frameId: 1,
          frameHandle: `${sessionId}:1`,
          frameTransport: "tcp-length-prefixed",
          payloadBytes: 0,
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
