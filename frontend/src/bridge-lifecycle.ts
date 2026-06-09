import type { BridgeEnvelope } from "./bridge";

export type BridgeStopCommand = (
  command: "job.stop",
  payload: { jobId: string },
  options: { jobId: string }
) => Promise<BridgeEnvelope>;

export async function stopJobById(
  sendCommand: BridgeStopCommand,
  jobId: string | null | undefined
): Promise<BridgeEnvelope | null> {
  if (!jobId) {
    return null;
  }
  return sendCommand("job.stop", { jobId }, { jobId });
}
