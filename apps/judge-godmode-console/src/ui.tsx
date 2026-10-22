import React, { useEffect, useRef } from "react";
import {
  AlertTriangle,
  Check,
  CheckCheck,
  CircleDashed,
  UserCheck,
  X,
} from "lucide-react";
import type {
  Contract,
  Evidence,
} from "../../../packages/physical-contract-schema";

export const fmt = (date: string) =>
  new Date(date).toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
export const day = (date: string) =>
  new Date(date).toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    weekday: "long",
    day: "numeric",
    month: "long",
  });
/** "18:00" today, "Thu 07:00" on another day (IST). */
export const due = (date: string, now: string) => {
  const opts = { timeZone: "Asia/Kolkata" } as const;
  const sameDay =
    new Date(date).toLocaleDateString("en-GB", opts) ===
    new Date(now).toLocaleDateString("en-GB", opts);
  return sameDay
    ? fmt(date)
    : new Date(date).toLocaleDateString("en-GB", {
        ...opts,
        weekday: "short",
      }) +
        " " +
        fmt(date);
};
export const human = (s: string) => s.toLowerCase().replaceAll("_", " ");

// Server copy is written for audit logs; the console shows it in product language.
const rewrites: [RegExp, string][] = [
  [/\bSCRIPTED clock\b/, "scripted clock"],
  [/\bWALL clock\b/, "wall clock"],
];
export const plain = (text: string) =>
  rewrites.reduce((t, [re, to]) => t.replace(re, to), text);
/** "scripted-porch" → "Front porch". */
export const cameraName = (id: string) => {
  const name = id.replace(/^scripted-/, "").replaceAll("-", " ");
  return name === "porch"
    ? "Front porch"
    : name.charAt(0).toUpperCase() + name.slice(1);
};
export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Fire OS / Android TV WebViews older than Chromium 92 lack crypto.randomUUID.
export const uuid = (): string => {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
};

export async function api(path: string, body?: unknown) {
  const response = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers:
      body === undefined
        ? {}
        : {
            "Content-Type": "application/json",
            "Idempotency-Key": uuid(),
          },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data: {
    error?: { message?: string };
    detail?: { msg?: string }[];
    [key: string]: unknown;
  } = {};
  try {
    data = await response.json();
  } catch {
    /* non-JSON error page */
  }
  if (!response.ok)
    throw new Error(
      plain(
        data.error?.message ??
          data.detail?.[0]?.msg ??
          `Request failed (${response.status})`,
      ),
    );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return data as any;
}

export const TERMINAL = ["VERIFIED", "CANCELLED", "REJECTED"];
export const isOpen = (c: Contract) => !TERMINAL.includes(c.status);

/** Owner-confirmable without sensor proof (mirrors the server's confirm-done policy). */
export const canConfirmDone = (c: Contract) =>
  c.key.startsWith("gen_") &&
  ["ACTIVE", "ENGAGED", "EVIDENCE_PENDING", "MISSED"].includes(c.status) &&
  c.verification_modality !== "FIRE_TV_LIVE_POSE_CAMERA";

export const userConfirmed = (c: Contract, evidence: Evidence[]) =>
  c.status === "VERIFIED" &&
  (c.verification_provenance
    ? c.verification_provenance === "USER_CONFIRMED"
    : evidence.some(
        (e) =>
          e.contract_id === c.contract_id &&
          e.provenance === "USER_CONFIRMED" &&
          c.evidence_ids.includes(e.evidence_id),
      ));
/** Sensor-backed closures only; owner confirmations are counted separately. */
export const sensorVerified = (c: Contract, evidence: Evidence[]) =>
  c.status === "VERIFIED" && !userConfirmed(c, evidence);

type Tone = "good" | "user" | "open" | "check" | "missed" | "muted";
const contractChip: Record<string, [Tone, string]> = {
  VERIFIED: ["good", "Verified by evidence"],
  NEEDS_CONFIRMATION: ["check", "Needs your check"],
  EVIDENCE_PENDING: ["check", "Needs your check"],
  DISPUTED: ["check", "Needs your check"],
  MISSED: ["missed", "Missed"],
  CANCELLED: ["muted", "Cancelled"],
  REJECTED: ["muted", "Declined"],
};
const toneIcon: Record<Tone, typeof Check> = {
  good: CheckCheck,
  user: UserCheck,
  open: CircleDashed,
  check: AlertTriangle,
  missed: X,
  muted: X,
};

/** Re-triggers the spring animation only when the value actually changes. */
function useChanged(value: string) {
  const previous = useRef(value);
  const changed = previous.current !== value;
  useEffect(() => {
    previous.current = value;
  }, [value]);
  return changed;
}

export function ContractChip({
  c,
  evidence,
}: {
  c: Contract;
  evidence: Evidence[];
}) {
  const byUser = userConfirmed(c, evidence);
  const [tone, label] = byUser
    ? (["user", "Confirmed by you"] as [Tone, string])
    : (contractChip[c.status] ?? ["open", "Not yet verified"]);
  const changed = useChanged(c.status + byUser);
  const Icon = toneIcon[tone];
  return (
    <span
      key={c.status}
      className={`chip ${tone} ${changed ? "pop" : ""}`}
      title={
        byUser
          ? "Confirmed by you · not sensor proof"
          : c.status === "VERIFIED" && c.verification_provenance
            ? `Verified · ${sourceWords(c.verification_provenance)}`
            : human(c.status)
      }
    >
      <Icon size={12} aria-hidden strokeWidth={2.4} />
      {label}
    </span>
  );
}

const genericTone = (status: string): Tone =>
  /^(VERIFIED|AUTHORIZED_TRANSFER|VERIFIED_SAFE_TRANSFER|REPLAY_VERIFIED|LIVE_VERIFIED|CONNECTED|REPORT_ACKNOWLEDGED)$/.test(
    status,
  )
    ? "good"
    : /AWAITING|DISPUTED|BLOCKED|PREPARED|APPROVED|MISMATCH/.test(status)
      ? "check"
      : /MISSED|FAILED|EXPIRED/.test(status)
        ? "missed"
        : /STANDBY|CANCELLED|REJECTED/.test(status)
          ? "muted"
          : "open";

const statusLabels: Record<string, string> = {
  LOCAL_DISPATCH: "sent to local receiver",
  REPLAY_VERIFIED: "ready",
  STANDBY: "ready to link",
  LIVE_VERIFIED: "live",
};

export function Status({ status }: { status: string }) {
  const tone = status === "LOCAL_DISPATCH" ? "good" : genericTone(status);
  const text = statusLabels[status] ?? human(status);
  const changed = useChanged(status);
  const Icon = toneIcon[tone];
  return (
    <span
      key={status}
      className={`chip ${tone} ${changed ? "pop" : ""}`}
      title={text}
    >
      <Icon size={12} aria-hidden strokeWidth={2.4} />
      {text}
    </span>
  );
}

const sourceLabels: Record<string, string> = {
  LIVE_VERIFIED: "Live camera",
  LIVE_SENSOR: "Live camera",
  REPLAY_VERIFIED: "Scripted replay",
  SCRIPTED: "Scripted replay",
  SCRIPTED_SENSOR: "Scripted replay",
  SCRIPTED_FIXTURE: "Scripted replay",
  RECORDED_WORKOUT_VIDEO: "Recorded workout video",
  RECORDED_WORKOUT: "Recorded workout video",
  REAL_RECORDED_STOCK: "Licensed public footage",
  USER_CONFIRMED: "Owner confirmation",
  USER_OVERRIDE: "Owner override",
  MCP_OWNER_INPUT: "Typed by you",
  STANDBY: "Ready to link",
  BLOCKED: "Blocked",
};

/** Provenance in plain words, for the Source row of detail views and the evidence packet. */
export const sourceWords = (mode?: string | null) =>
  sourceLabels[mode ?? ""] ??
  (mode ? mode.charAt(0) + human(mode).slice(1) : "Unknown");

export const contractSource = (c: Contract) =>
  c.scene_source?.source ?? c.source_mode;

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "compact" : ""}`}>
      <span className="brand-symbol" aria-hidden>
        <CheckCheck size={compact ? 16 : 18} strokeWidth={2.6} />
      </span>
      <strong>Muni</strong>
    </div>
  );
}

export function Empty({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Check;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon size={20} aria-hidden />
      </span>
      <h3>{title}</h3>
      {children}
    </div>
  );
}
