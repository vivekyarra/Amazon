// Alexa+ web experience — deterministic agentic router over the Muni MCP server.
// No LLM and no Alexa device: typed or browser-recognized speech is matched to intents with
// fixed rules, and each intent is answered only from real JSON-RPC tool results returned by
// /mcp (same origin, authenticated by the judge session cookie).

import { plain, uuid } from "./ui";
export const PROTOCOL_VERSION = "2025-11-25";

export type RpcLogEntry = {
  id: number;
  at: string;
  tool?: string;
  status: number;
  ms: number;
  request: unknown;
  response: unknown;
};

type Logger = (entry: RpcLogEntry) => void;

let nextId = 1;
let negotiated: string | null = null;

async function post(body: Record<string, unknown>, log: Logger, tool?: string) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  if (negotiated) headers["MCP-Protocol-Version"] = negotiated;
  const started = performance.now();
  const response = await fetch("/mcp/", {
    method: "POST",
    credentials: "same-origin",
    headers,
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  log({
    id: nextId,
    at: new Date().toISOString(),
    tool,
    status: response.status,
    ms: Math.round(performance.now() - started),
    request: body,
    response: data,
  });
  if (!response.ok && response.status !== 202) {
    const message =
      (data as { error?: { message?: string } })?.error?.message ??
      `MCP HTTP ${response.status}`;
    throw new Error(message);
  }
  return data as {
    result?: Record<string, unknown>;
    error?: { code: number; message: string };
  } | null;
}

async function rpc(
  method: string,
  params: Record<string, unknown>,
  log: Logger,
  tool?: string,
) {
  const data = await post(
    { jsonrpc: "2.0", id: nextId++, method, params },
    log,
    tool,
  );
  if (data?.error)
    throw new Error(`JSON-RPC ${data.error.code}: ${data.error.message}`);
  return data?.result ?? {};
}

export async function ensureInitialized(log: Logger) {
  if (negotiated) return negotiated;
  const result = await rpc(
    "initialize",
    {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: "muni-alexa-web", version: "1.0.0" },
    },
    log,
  );
  negotiated = String(result.protocolVersion);
  await post({ jsonrpc: "2.0", method: "notifications/initialized" }, log);
  return negotiated;
}

export async function callTool<T = Record<string, any>>(
  name: string,
  args: Record<string, unknown>,
  log: Logger,
): Promise<T> {
  await ensureInitialized(log);
  const result = (await rpc(
    "tools/call",
    { name, arguments: args },
    log,
    name,
  )) as {
    isError?: boolean;
    structuredContent?: T;
    content?: { type: string; text: string }[];
  };
  const text = result.content?.[0]?.text ?? "";
  if (result.isError) throw new Error(text || "Tool returned an error.");
  if (result.structuredContent) return result.structuredContent;
  return JSON.parse(text) as T;
}

export type Intent =
  | "promises"
  | "parcel"
  | "reality_lock"
  | "sister"
  | "police"
  | "health"
  | "remember"
  | "help";

export function routeIntent(raw: string): { intent: Intent; text: string } {
  const text = raw
    .trim()
    .replace(/^(hey\s+)?alexa[,\s]*/i, "")
    .replace(/[?.!]+$/, "")
    .trim();
  const t = text.toLowerCase().replace(/’/g, "'");
  if (/^(remember|note|remind me|make a note)\b/.test(t))
    return { intent: "remember", text };
  if (/\b(police|report|file a complaint)\b/.test(t))
    return { intent: "police", text };
  if (/\b(parcel|package|porch|delivery|courier)\b/.test(t))
    return { intent: "parcel", text };
  if (/\b(reality[- ]?lock|squats?|workout|unlock)\b/.test(t))
    return { intent: "reality_lock", text };
  if (/\bsister\b/.test(t)) return { intent: "sister", text };
  if (/\b(connected|integrations?|devices?|health)\b/.test(t))
    return { intent: "health", text };
  if (
    /\b(promise|promised|commitments?|to-?do|what do i (have|owe)|today)\b/.test(
      t,
    )
  )
    return { intent: "promises", text };
  return { intent: "help", text };
}

type C = {
  contract_id: string;
  key: string;
  title: string;
  status: string;
  due_at: string | null;
  custody_status?: string;
  deposit_status?: string;
};

const clock = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      })
    : "";

const statusWords: Record<string, string> = {
  VERIFIED: "verified by evidence",
  ACTIVE: "not yet verified",
  ENGAGED: "in progress, not yet verified",
  NEEDS_CONFIRMATION: "waiting for your confirmation",
  EVIDENCE_PENDING: "evidence pending",
  DISPUTED: "disputed",
  MISSED: "missed — no accepted proof by the deadline",
  CANCELLED: "cancelled",
  REJECTED: "rejected",
};

async function contracts(log: Logger) {
  const data = await callTool<{
    contracts: C[];
    tv_sessions: { session_id: string }[];
  }>("list_active_contracts", {}, log);
  return data;
}

export const EXAMPLES = [
  "Alexa, what did I promise today?",
  "Alexa, is my parcel safe?",
  "Alexa, start Reality-Lock",
  "Alexa, did I call my sister?",
];

export async function answer(
  raw: string,
  log: Logger,
): Promise<{ intent: Intent; reply: string }> {
  const { intent, text } = routeIntent(raw);
  const reply = await (async () => {
    switch (intent) {
      case "promises": {
        const { contracts: list } = await contracts(log);
        if (!list.length)
          return "I don't see any promises in your household ledger yet. Run the 8:15 AM morning scenario first.";
        const verified = list.filter((c) => c.status === "VERIFIED").length;
        const items = list
          .map(
            (c) =>
              `${c.title}${c.due_at ? ` (due ${clock(c.due_at)})` : ""}: ${statusWords[c.status] ?? c.status.toLowerCase()}`,
          )
          .join("; ");
        return `You have ${list.length} tracked commitment${list.length === 1 ? "" : "s"}, ${verified} verified by evidence. ${items}.`;
      }
      case "parcel": {
        const { contracts: list } = await contracts(log);
        const parcel = list.find((c) => c.key === "parcel");
        if (!parcel)
          return "I'm not tracking a parcel yet. No courier event has been processed today.";
        const detail = await callTool<{ contract: C; incident_ids: string[] }>(
          "get_contract_state",
          { contract_id: parcel.contract_id },
          log,
        );
        const watch = await callTool<{
          subagents: { kind: string; status: string }[];
        }>("get_watchdog_status", { contract_id: parcel.contract_id }, log);
        const c = detail.contract;
        const dog = watch.subagents.find((a) => a.kind === "PorchWatchdog");
        if (detail.incident_ids.length) {
          const packet = await callTool<{
            incident: { status: string };
            official_case_id: string | null;
          }>(
            "get_incident_packet",
            { incident_id: detail.incident_ids[0] },
            log,
          );
          return `A person moved the package from the porch. Was this authorized? The incident is ${packet.incident.status.toLowerCase().replaceAll("_", " ")}; review the evidence in the console. I can't confirm custody or file anything by voice.`;
        }
        if (c.deposit_status === "DELIVERY_MISMATCH")
          return "Courier said the package was left, but I could not confirm a deposit. Review the camera evidence.";
        if (c.custody_status === "DEPOSIT_VERIFIED_CUSTODY_ACTIVE")
          return `Parcel was observed on your porch. PorchWatchdog is ${dog ? dog.status.toLowerCase() : "not running"}; custody is not yet complete.`;
        return `The parcel is ${statusWords[c.status] ?? c.status.toLowerCase()}. Custody status: ${(c.custody_status ?? "unknown").toLowerCase().replaceAll("_", " ")}.`;
      }
      case "reality_lock": {
        const { contracts: list, tv_sessions } = await contracts(log);
        const squats = list.find((c) => c.key === "squats");
        const bridge = await callTool<{ status: string; reason?: string }>(
          "bridge_ring_camera_to_firetv",
          {
            camera_device_id: "scripted-porch",
            firetv_session_id: tv_sessions[0]?.session_id ?? "none",
            verification_mode: "POSE_SQUATS",
          },
          log,
        );
        const promise = squats
          ? `Your squats promise is ${statusWords[squats.status] ?? squats.status.toLowerCase()}.`
          : "There is no squats promise in the ledger yet.";
        if (bridge.status === "BLOCKED")
          return `I can't open a live Ring-to-Fire TV camera relay here: the live camera isn't connected. ${promise} You can still run the workout in the Reality-Lock studio.`;
        return `Reality-Lock bridge status: ${bridge.status.toLowerCase()}. ${promise}`;
      }
      case "sister": {
        const { contracts: list } = await contracts(log);
        const sister = list.find((c) => c.key === "sister");
        if (!sister)
          return "I don't have a promise to call your sister in today's ledger.";
        const detail = await callTool<{ contract: C }>(
          "get_contract_state",
          { contract_id: sister.contract_id },
          log,
        );
        const c = detail.contract;
        if (c.status === "VERIFIED")
          return "Yes. The call to your sister is verified by recorded evidence.";
        if (c.status === "MISSED")
          return `Not that I can verify. No accepted proof arrived before ${clock(c.due_at)}, so it's marked missed. Late proof can still be added.`;
        const verify = await callTool<{ prompt: string }>(
          "request_user_verification",
          { contract_id: sister.contract_id },
          log,
        );
        return `Not yet verified${c.due_at ? `; it's due by ${clock(c.due_at)}` : ""}. ${verify.prompt}`;
      }
      case "police": {
        const { contracts: list } = await contracts(log);
        const parcel = list.find((c) => c.key === "parcel");
        const ids = parcel
          ? (
              await callTool<{ incident_ids: string[] }>(
                "get_contract_state",
                { contract_id: parcel.contract_id },
                log,
              )
            ).incident_ids
          : [];
        if (!ids.length) return "There is no incident to report.";
        const result = await callTool<{ status: string; reason: string }>(
          "dispatch_police_evidence_dossier",
          { incident_id: ids[0], human_confirmed_boolean: true },
          log,
        );
        return `I can't file a police report from a voice command. The server answered ${result.status.toLowerCase()}: ${result.reason} Nothing was sent.`;
      }
      case "health": {
        const data = await callTool<{
          integrations: { name: string; status: string }[];
        }>("get_integration_health", {}, log);
        return (
          data.integrations
            .map(
              (i) =>
                `${i.name}: ${i.status === "REPLAY_VERIFIED" ? "ready" : i.status.toLowerCase().replaceAll("_", " ")}`,
            )
            .join("; ") + "."
        );
      }
      case "remember": {
        const utterance = text.replace(
          /^(remember|note|remind me|make a note)\b[:,]?\s*(that\s+)?/i,
          "",
        );
        const result = await callTool<{ contract_ids: string[] }>(
          "compile_ambient_commitment",
          {
            utterance_json: {
              event_id: "alexa-web-" + uuid(),
              utterance,
              occurred_at: new Date().toISOString(),
            },
            speaker_context: { speaker: "SELF" },
          },
          log,
        );
        return result.contract_ids.length
          ? `Noted as owner-typed text, not a Bee capture: ${result.contract_ids.join(", ")}. It stays unverified until evidence arrives.`
          : "I didn't hear a commitment I can track. Try a phrase like \"I'll call my sister before 6 PM\".";
      }
      default:
        return `I can answer: ${EXAMPLES.map((e) => `"${e.replace(/^Alexa, /, "")}"`).join(", ")}.`;
    }
  })();
  return { intent, reply: plain(reply) };
}

const TEACHER_T25 =
  "Your teacher meeting begins in 25 minutes, and I haven't confirmed you're preparing. Open meeting details?";

export function whisperCopy(
  alert: { kind: string; message: string; contract_id: string },
  contractKey?: string,
) {
  if (alert.kind === "ACTIVE_ESCALATION" && contractKey === "teacher")
    return TEACHER_T25;
  return alert.message;
}
