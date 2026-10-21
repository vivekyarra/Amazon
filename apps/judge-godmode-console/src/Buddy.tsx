import React, { useState } from "react";
import {
  AlarmClock,
  ArrowUp,
  CalendarClock,
  Check,
  CheckCheck,
  Hourglass,
  Inbox,
  Repeat,
  X,
} from "lucide-react";
import type {
  Contract,
  State,
} from "../../../packages/physical-contract-schema";
import {
  ContractChip,
  Empty,
  SourceTag,
  canConfirmDone,
  contractSource,
  fmt,
  human,
  isOpen,
} from "./ui";

type Act = (path: string, body?: unknown) => Promise<unknown>;

const triggerCopy: Record<string, string> = {
  ARRIVAL_HOME: "When you arrive home",
  BEFORE_ENTERTAINMENT: "Before TV",
  AUTHORIZED_INWARD_TRANSFER: "Until brought inside",
};

function relative(due: string, now: number) {
  const minutes = Math.round((new Date(due).getTime() - now) / 60000);
  if (minutes < 0) {
    const late = -minutes;
    return late < 60
      ? `${late} min overdue`
      : `${Math.round(late / 60)} h overdue`;
  }
  if (minutes < 60) return `in ${minutes} min`;
  if (minutes < 24 * 60) return `in ${Math.round(minutes / 60)} h`;
  return `in ${Math.round(minutes / 1440)} d`;
}

const sameDay = (a: string, b: string) =>
  new Date(a).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata" }) ===
  new Date(b).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata" });

/** Everyday-buddy view for a real (wall-clock) household. */
export function Buddy({
  state,
  act,
  busy,
  guarded,
  onOpen,
}: {
  state: State;
  act: Act;
  busy: boolean;
  guarded: (fn: () => Promise<unknown>) => Promise<void>;
  onOpen: (c: Contract) => void;
}) {
  const [text, setText] = useState("");
  const [added, setAdded] = useState("");
  const now = new Date(state.now).getTime();
  const open = state.contracts.filter(isOpen);
  const awaiting = open.filter((c) =>
    ["NEEDS_CONFIRMATION", "EVIDENCE_PENDING", "DISPUTED"].includes(c.status),
  );
  const rest = open.filter((c) => !awaiting.includes(c));
  const overdue = rest.filter(
    (c) =>
      c.status === "MISSED" || (c.due_at && new Date(c.due_at).getTime() < now),
  );
  const upcoming = rest.filter((c) => !overdue.includes(c));
  const recurringOrLater = upcoming.filter(
    (c) =>
      c.recurrence ||
      (c.due_at ? !sameDay(c.due_at, state.now) : !c.deadline_trigger),
  );
  const today = upcoming
    .filter((c) => !recurringOrLater.includes(c))
    .sort(
      (a, b) =>
        (a.due_at ? new Date(a.due_at).getTime() : Infinity) -
        (b.due_at ? new Date(b.due_at).getTime() : Infinity),
    );
  const done = state.contracts.filter((c) => c.status === "VERIFIED").reverse();
  const soon = today.filter(
    (c) => c.due_at && new Date(c.due_at).getTime() - now < 2 * 3600 * 1000,
  ).length;

  const confirm = (c: Contract, action: string) =>
    guarded(() =>
      act(`/contracts/${c.contract_id}/confirm`, {
        action,
        revision: c.revision,
      }),
    );

  const card = (c: Contract) => {
    const dueSoon =
      c.due_at &&
      isOpen(c) &&
      new Date(c.due_at).getTime() - now < 2 * 3600 * 1000 &&
      new Date(c.due_at).getTime() >= now;
    return (
      <article className="buddy-card" key={c.contract_id}>
        <button
          className="buddy-card-main"
          onClick={() => onOpen(c)}
          aria-label={`${c.title}, open details`}
        >
          <strong>{c.title}</strong>
          <span className="buddy-when">
            {c.due_at ? (
              <>
                <CalendarClock size={13} aria-hidden />
                {fmt(c.due_at)}
                {isOpen(c) && (
                  <em className={dueSoon ? "soon" : ""}>
                    {relative(c.due_at, now)}
                  </em>
                )}
              </>
            ) : (
              <>
                <AlarmClock size={13} aria-hidden />
                {triggerCopy[c.deadline_trigger ?? ""] ??
                  human(c.deadline_trigger ?? "No deadline")}
              </>
            )}
            {c.recurrence && (
              <span className="buddy-repeat">
                <Repeat size={12} aria-hidden /> {human(c.recurrence.freq)}
              </span>
            )}
          </span>
        </button>
        {c.proposed_amendment && (
          <p className="buddy-amend">
            New deadline proposed: {fmt(c.proposed_amendment.due_at)} · not
            applied
          </p>
        )}
        <div className="buddy-card-meta">
          <ContractChip c={c} evidence={state.evidence} />
          <SourceTag mode={contractSource(c)} />
        </div>
        {(c.status === "NEEDS_CONFIRMATION" ||
          canConfirmDone(c) ||
          (c.key === "drinks" && isOpen(c))) && (
          <div className="buddy-actions">
            {c.status === "NEEDS_CONFIRMATION" ? (
              <>
                <button
                  className="button primary small"
                  disabled={busy}
                  onClick={() => void confirm(c, "accept")}
                  aria-label={`Accept: ${c.title}`}
                >
                  <Check size={14} aria-hidden /> Accept
                </button>
                <button
                  className="button small"
                  disabled={busy}
                  onClick={() => void confirm(c, "reject")}
                  aria-label={`Decline: ${c.title}`}
                >
                  <X size={14} aria-hidden /> Decline
                </button>
              </>
            ) : (
              <button
                className="button small"
                disabled={busy}
                onClick={() =>
                  void confirm(
                    c,
                    c.key === "drinks" ? "confirm-drinks" : "confirm-done",
                  )
                }
                aria-label={`Confirm done: ${c.title}`}
                title="Recorded as USER_CONFIRMED, not sensor proof"
              >
                <CheckCheck size={14} aria-hidden /> Confirm done
              </button>
            )}
          </div>
        )}
      </article>
    );
  };

  const columns: [string, typeof Inbox, Contract[], string][] = [
    ["Awaiting your check", Inbox, awaiting, "Nothing waiting on you."],
    ["Due today", CalendarClock, today, "Nothing else due today."],
    ["Overdue", Hourglass, overdue, "Nothing overdue."],
    ["Recurring & later", Repeat, recurringOrLater, "No recurring promises."],
    ["Done", CheckCheck, done, "Closed promises appear here."],
  ];

  const briefing = [...state.alerts]
    .reverse()
    .find((a) => a.kind === "DAILY_BRIEFING" && sameDay(a.at, state.now));
  return (
    <div className="buddy">
      {briefing && (
        <p className="briefing" role="status">
          <span className="kind" data-kind="DAILY_BRIEFING">
            Your day · {fmt(briefing.at)}
          </span>
          {briefing.message}
        </p>
      )}
      <form
        className="add-promise"
        onSubmit={(ev) => {
          ev.preventDefault();
          const utterance = text.trim();
          if (!utterance) return;
          void guarded(async () => {
            const d = (await act("/owner/promises", {
              utterance,
              timezone: "Asia/Kolkata",
            })) as { result?: { contract_ids?: string[] } };
            setText("");
            setAdded(
              d.result?.contract_ids?.length
                ? "Added. It closes only with evidence or your confirmation."
                : "No promise found in that sentence. Try “I’ll … by 6 pm”.",
            );
          });
        }}
      >
        <label className="sr-only" htmlFor="add-promise-input">
          Add a promise
        </label>
        <input
          id="add-promise-input"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setAdded("");
          }}
          placeholder="Add a promise — “I’ll pay the electricity bill by 6 pm”"
          maxLength={4000}
          disabled={!state.consent}
        />
        <SourceTag
          mode="MCP_OWNER_INPUT"
          title="Typed by you · compiled by the same MCP compiler"
        />
        <button
          className="button primary"
          disabled={busy || !text.trim() || !state.consent}
        >
          <ArrowUp size={15} aria-hidden /> Add promise
        </button>
        <p className="add-note" role="status">
          {state.consent &&
            (added || (soon ? `${soon} due within 2 hours.` : ""))}
        </p>
      </form>
      <div className="buddy-board">
        {columns.map(([title, Icon, items, empty]) => (
          <section
            className="buddy-col"
            key={title}
            aria-label={title}
            data-kind={title === "Overdue" ? "overdue" : undefined}
          >
            <header>
              <Icon size={15} aria-hidden />
              <h2>{title}</h2>
              <span className="count">{items.length}</span>
            </header>
            <div className="buddy-list">
              {items.length ? (
                items.map(card)
              ) : (
                <Empty icon={Icon} title={empty} />
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
