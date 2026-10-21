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
      data.error?.message ??
        data.detail?.[0]?.msg ??
        `Request failed (${response.status})`,
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
    <>
      <span
        key={c.status}
        className={`chip ${tone} ${changed ? "pop" : ""}`}
        title={
          byUser
            ? "USER_CONFIRMED · not sensor proof"
            : c.status === "VERIFIED" && c.verification_provenance
              ? `${c.status} · ${c.verification_provenance}`
              : c.status
        }
      >
        <Icon size={12} aria-hidden strokeWidth={2.4} />
        {label}
      </span>
      {byUser && (
        <SourceTag
          mode="USER_CONFIRMED"
          title="Owner confirmation, not sensor proof"
        />
      )}
    </>
  );
}

const genericTone = (status: string): Tone =>
  /^(VERIFIED|AUTHORIZED_TRANSFER|VERIFIED_SAFE_TRANSFER|SIMULATED_VERIFIED|LIVE_VERIFIED|CONNECTED|REPORT_ACKNOWLEDGED)$/.test(
    status,
  )
    ? "good"
    : /AWAITING|DISPUTED|BLOCKED|PREPARED|APPROVED|MISMATCH/.test(status)
      ? "check"
      : /MISSED|FAILED|EXPIRED/.test(status)
        ? "missed"
        : /NOT_CONNECTED|CANCELLED|REJECTED/.test(status)
          ? "muted"
          : "open";

export function Status({ status }: { status: string }) {
  const tone = genericTone(status);
  const changed = useChanged(status);
  const Icon = toneIcon[tone];
  return (
    <span
      key={status}
      className={`chip ${tone} ${changed ? "pop" : ""}`}
      title={status}
    >
      <Icon size={12} aria-hidden strokeWidth={2.4} />
      {human(status)}
    </span>
  );
}

const sourceLabels: Record<string, [string, string]> = {
  LIVE_VERIFIED: ["LIVE", "live"],
  SIMULATED_VERIFIED: ["SIMULATED", "sim"],
  SYNTHETIC: ["SIMULATED", "sim"],
  RECORDED_DEMO_VIDEO: ["RECORDED DEMO", "rec"],
  RECORDED_DEMO: ["RECORDED DEMO", "rec"],
  REAL_RECORDED_STOCK: ["REAL_RECORDED_STOCK", "rec"],
  USER_CONFIRMED: ["USER_CONFIRMED", "user"],
  MCP_OWNER_INPUT: ["MCP_OWNER_INPUT", "user"],
  NOT_CONNECTED: ["NOT CONNECTED", "off"],
  BLOCKED: ["BLOCKED", "off"],
};

/** Truthful provenance label. LIVE appears only for LIVE_VERIFIED sources. */
export function SourceTag({
  mode,
  title,
}: {
  mode?: string | null;
  title?: string;
}) {
  const [label, tone] = sourceLabels[mode ?? ""] ?? [
    (mode ?? "UNKNOWN").replaceAll("_", " "),
    "off",
  ];
  return (
    <span className={`source ${tone}`} title={title ?? mode ?? undefined}>
      {label}
    </span>
  );
}

export const contractSource = (c: Contract) =>
  c.scene_source?.source ?? c.source_mode;

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "compact" : ""}`}>
      <span className="brand-symbol" aria-hidden>
        <CheckCheck size={compact ? 16 : 18} strokeWidth={2.6} />
      </span>
      <strong>
        DONE<span>/</span>IRL
      </strong>
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
