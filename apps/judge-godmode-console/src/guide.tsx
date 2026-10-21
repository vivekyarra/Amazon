import React, { useState } from "react";
import {
  AlertTriangle,
  AudioLines,
  CheckCheck,
  CircleDashed,
  Keyboard,
  Play,
  Plus,
  ScanLine,
  ShieldCheck,
  UserCheck,
  X,
} from "lucide-react";
import type {
  Contract,
  Evidence,
} from "../../../packages/physical-contract-schema";
import { human, userConfirmed } from "./ui";

/** Verification policies in product words (the raw modality stays in the MCP payloads). */
const modalityWords: Record<string, string> = {
  BEE_CONVERSATION_AUDIT: "Conversation heard by Bee",
  RING_THRESHOLD_OBJECT_SCAN: "Doorway camera, then your confirmation",
  RING_SPATIAL_CUSTODY: "Porch camera custody",
  FIRE_TV_LIVE_POSE_CAMERA: "Camera-counted squats (Reality-Lock)",
  AUTHORIZED_MANUAL_CONFIRMATION: "Your confirmation",
};
export const modalityText = (m: string) => modalityWords[m] ?? human(m);

/** What evidence would close this promise, in one sentence. */
function requirement(c: Contract) {
  const who = c.counterparty.label;
  switch (c.verification_modality) {
    case "BEE_CONVERSATION_AUDIT":
      return c.key === "teacher"
        ? "a Bee transcript showing you took part in the meeting"
        : `a Bee transcript of the conversation with ${who.toLowerCase() === "self" ? "them" : who}`;
    case "RING_THRESHOLD_OBJECT_SCAN":
      return "your confirmation that you have them. The doorway camera can only support it, never close it";
    case "RING_SPATIAL_CUSTODY":
      return "an authorized handover: you or family picking the parcel up from the porch";
    case "FIRE_TV_LIVE_POSE_CAMERA":
      return "full squats counted from the camera in Reality-Lock studio";
    case "AUTHORIZED_MANUAL_CONFIRMATION":
      return "your confirmation. It is recorded as owner confirmation, never as sensor proof";
    default:
      return `evidence matching its policy (${human(c.verification_modality)})`;
  }
}

type Tone = "good" | "user" | "open" | "check" | "missed" | "muted";
const toneIcon: Record<Tone, typeof CheckCheck> = {
  good: CheckCheck,
  user: UserCheck,
  open: CircleDashed,
  check: AlertTriangle,
  missed: X,
  muted: X,
};

/** The "never fake done" explanation shown on every contract detail. */
export function Verdict({
  c,
  evidence,
  onStudio,
}: {
  c: Contract;
  evidence: Evidence[];
  onStudio?: () => void;
}) {
  const linked = evidence.filter((e) => c.evidence_ids.includes(e.evidence_id));
  let tone: Tone, title: string, body: string;
  if (c.status === "VERIFIED" && userConfirmed(c, evidence)) {
    tone = "user";
    title = "Closed by your confirmation";
    body =
      "You confirmed this yourself. It is labelled as owner confirmation and never counted as sensor proof.";
  } else if (c.status === "VERIFIED") {
    tone = "good";
    title = "Done, proven by evidence";
    body = linked.length
      ? `Closed by ${linked.map((e) => human(e.kind)).join(", ")}. Each artifact is hashed in the evidence packet.`
      : "Closed by evidence that satisfied its verification policy.";
  } else if (c.status === "MISSED") {
    tone = "missed";
    title = "Missed: no accepted proof by the deadline";
    body = `It needed ${requirement(c)}. Nothing was marked done without it.`;
  } else if (c.status === "NEEDS_CONFIRMATION") {
    tone = "check";
    title = "Waiting for you to accept it";
    body =
      "The wording was ambiguous, so it is not tracked until you accept it.";
  } else if (c.status === "CANCELLED" || c.status === "REJECTED") {
    tone = "muted";
    title = c.status === "CANCELLED" ? "Cancelled" : "Declined";
    body = "No longer tracked. Its history stays in the ledger.";
  } else {
    tone =
      c.status === "EVIDENCE_PENDING" || c.status === "DISPUTED"
        ? "check"
        : "open";
    title = "Why not done yet";
    body = `Needs ${requirement(c)}. Saying it is done is not enough.`;
  }
  const Icon = toneIcon[tone];
  return (
    <div className={`verdict ${tone}`} role="note" aria-label={title}>
      <Icon size={16} aria-hidden strokeWidth={2.4} />
      <div>
        <strong>{title}</strong>
        <p>{body}</p>
        {onStudio &&
          c.verification_modality === "FIRE_TV_LIVE_POSE_CAMERA" &&
          c.status !== "VERIFIED" && (
            <button className="text-button" onClick={onStudio}>
              Open Reality-Lock studio
            </button>
          )}
      </div>
    </div>
  );
}

/** One form for typed promises; it runs the same compiler as the morning stream. */
export function AddPromise({
  admin,
  now,
  consent,
  busy,
  act,
  guarded,
  className = "",
  newId,
}: {
  admin: boolean;
  now: string;
  consent: boolean;
  busy: boolean;
  act: (path: string, body?: unknown) => Promise<unknown>;
  guarded: (fn: () => Promise<unknown>) => Promise<void>;
  className?: string;
  newId: () => string;
}) {
  const [text, setText] = useState("");
  return (
    <form
      className={`add-promise ${className}`}
      onSubmit={(ev) => {
        ev.preventDefault();
        void guarded(async () => {
          if (admin)
            await act("/ingest/bee-simulated", {
              event_id: newId(),
              utterance: text,
              speaker: "SELF",
              counterparty: "Household",
              occurred_at: now,
              timezone: "Asia/Kolkata",
            });
          else
            await act("/owner/promises", {
              utterance: text,
              timezone: "Asia/Kolkata",
            });
          setText("");
        });
      }}
    >
      <input
        aria-label="A new promise, in your own words"
        value={text}
        onChange={(ev) => setText(ev.target.value)}
        placeholder="“I’ll call my sister before 7 PM.”"
        required
        maxLength={4000}
      />
      <button className="button primary small" disabled={busy || !consent}>
        <Plus size={15} aria-hidden />
        Compile
      </button>
    </form>
  );
}

/** First-run guide on Mission control: three steps from nothing to proof. */
export function StartHere({
  onPlay,
  onOpen,
  disabled,
  children,
}: {
  onPlay: () => void;
  onOpen: (page: "incidents" | "alexa" | "studio") => void;
  disabled: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="start-here" aria-label="Start here" role="group">
      <div className="start-head">
        <span className="eyebrow">Start here · about 90 seconds</span>
        <h3>Watch one household day keep score.</h3>
      </div>
      <ol className="start-steps">
        <li>
          <div>
            <strong>
              <span className="step-n" aria-hidden>
                1
              </span>
              Play the day
            </strong>
            <p className="step-detail">
              Spoken promises compile into contracts, then porch, deadline and
              doorway scenes run against them.
            </p>
            <button
              className="button primary small"
              disabled={disabled}
              onClick={onPlay}
            >
              <Play size={13} fill="currentColor" aria-hidden />
              Play the whole day
            </button>
          </div>
        </li>
        <li>
          <div>
            <strong>
              <span className="step-n" aria-hidden>
                2
              </span>
              See what is proven, and what is not
            </strong>
            <p>A promise never turns green because someone said so.</p>
            <ul className="legend">
              <li>
                <span className="chip good">
                  <CheckCheck size={12} aria-hidden strokeWidth={2.4} />
                  Verified by evidence
                </span>
                <span className="legend-note">camera, pose or transcript</span>
              </li>
              <li>
                <span className="chip user">
                  <UserCheck size={12} aria-hidden strokeWidth={2.4} />
                  Confirmed by you
                </span>
                <span className="legend-note">never counted as proof</span>
              </li>
              <li>
                <span className="chip open">
                  <CircleDashed size={12} aria-hidden strokeWidth={2.4} />
                  Not yet verified
                </span>
                <span className="legend-note">still open</span>
              </li>
            </ul>
          </div>
        </li>
        <li>
          <div>
            <strong>
              <span className="step-n" aria-hidden>
                3
              </span>
              Open the proof
            </strong>
            <p className="step-detail">
              Every answer traces back to an artifact or a tool call.
            </p>
            <div className="start-links">
              <button
                className="button small"
                onClick={() => onOpen("incidents")}
              >
                <ShieldCheck size={14} aria-hidden /> Evidence
              </button>
              <button className="button small" onClick={() => onOpen("alexa")}>
                <AudioLines size={14} aria-hidden /> Alexa+ over MCP
              </button>
              <button className="button small" onClick={() => onOpen("studio")}>
                <ScanLine size={14} aria-hidden /> Studio
              </button>
            </div>
          </div>
        </li>
      </ol>
      {children}
      <p className="start-foot">
        <Keyboard size={13} aria-hidden />
        Shortcuts: <kbd>1</kbd>–<kbd>6</kbd> switch views · <kbd>Esc</kbd>{" "}
        closes panels
      </p>
    </div>
  );
}
