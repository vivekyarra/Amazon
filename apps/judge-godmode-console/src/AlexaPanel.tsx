import React, { useEffect, useRef, useState } from "react";
import { AudioLines, Mic, MicOff, Send, Volume2, VolumeX } from "lucide-react";
import type { State } from "../../../packages/physical-contract-schema";
import { EXAMPLES, answer, whisperCopy, type RpcLogEntry } from "./alexaClient";
import { plain } from "./ui";
import "./alexa.css";

type Turn = {
  id: number;
  who: "you" | "alexa";
  text: string;
  intent?: string;
  tools?: string[];
  error?: boolean;
};

type RpcBody = {
  method?: string;
  params?: { name?: string; arguments?: Record<string, unknown> };
};
type RpcReply = {
  result?: {
    structuredContent?: unknown;
    content?: { text?: string }[];
    protocolVersion?: string;
    serverInfo?: { name?: string };
    isError?: boolean;
  };
  error?: { message?: string };
} | null;

const short = (v: unknown): string => {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
  if (typeof v === "object") return `${Object.keys(v).length} fields`;
  const raw = String(v);
  // Enum values (REPLAY_VERIFIED, AWAITING_HUMAN_DECISION) read as words.
  const t = /^[A-Z][A-Z_]+$/.test(raw)
    ? plain(raw.replaceAll("_", " ")).toLowerCase()
    : plain(raw);
  return t.length > 42 ? t.slice(0, 40) + "…" : t;
};

/** A tool result as a handful of readable rows (the raw JSON stays one click away). */
function resultRows(response: unknown): [string, string][] {
  const r = (response as RpcReply)?.result;
  if (!r) return [];
  if (r.protocolVersion)
    return [
      ["protocol", r.protocolVersion],
      ["server", r.serverInfo?.name ?? "—"],
    ];
  let data: unknown = r.structuredContent;
  if (data === undefined) {
    try {
      data = JSON.parse(r.content?.[0]?.text ?? "");
    } catch {
      data = r.content?.[0]?.text;
    }
  }
  if (data && typeof data === "object" && !Array.isArray(data))
    return Object.entries(data as Record<string, unknown>)
      .slice(0, 4)
      .map(([k, v]) => [k, short(v)]);
  return data === undefined ? [] : [["result", short(data)]];
}

type Recognition = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function recognitionCtor(): (new () => Recognition) | null {
  const w = window as unknown as Record<string, unknown>;
  return (
    ((w.SpeechRecognition ??
      w.webkitSpeechRecognition) as new () => Recognition) ?? null
  );
}

function speak(text: string, enabled: boolean) {
  if (!enabled || !("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02;
    window.speechSynthesis.speak(u);
  } catch {
    /* speech output is optional; text is always shown */
  }
}

// The conversation survives moving between the replay console and the Alexa+ page.
const memory: { turns: Turn[]; log: RpcLogEntry[]; id: number } = {
  turns: [],
  log: [],
  id: 0,
};
/** Forget the conversation (on sign-out it must not leak to the next account). */
export function resetAlexaMemory() {
  memory.turns = [];
  memory.log = [];
  memory.id = 0;
}

export default function AlexaPanel({
  state,
  compact = false,
}: {
  state: State;
  compact?: boolean;
}) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>(memory.turns);
  const [log, setLog] = useState<RpcLogEntry[]>(memory.log);
  useEffect(() => {
    memory.turns = turns;
    memory.log = log;
  }, [turns, log]);
  const [busy, setBusy] = useState(false);
  const [voiceOut, setVoiceOut] = useState(true);
  const [listening, setListening] = useState(false);
  const [micNote, setMicNote] = useState("");
  const recognizer = useRef<Recognition | null>(null);
  const turnId = useRef(memory.id);
  useEffect(() => () => void (memory.id = turnId.current), []);
  const turnsEnd = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = turnsEnd.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length]);
  const seenAlerts = useRef<Set<string> | null>(null);
  const Ctor = recognitionCtor();

  const whispers = state.alerts
    .filter(
      (a) => a.kind === "ACTIVE_ESCALATION" || a.kind === "ARRIVAL_ITEM_CHECK",
    )
    .map((a) => ({
      ...a,
      copy: whisperCopy(
        a,
        state.contracts.find((c) => c.contract_id === a.contract_id)?.key,
      ),
    }));

  // Speak only whispers that arrive while the panel is open (not historical ones).
  useEffect(() => {
    const ids = new Set(whispers.map((w) => w.alert_id));
    if (seenAlerts.current === null) {
      seenAlerts.current = ids;
      return;
    }
    const fresh = whispers.filter((w) => !seenAlerts.current!.has(w.alert_id));
    seenAlerts.current = ids;
    if (fresh.length) speak(fresh[fresh.length - 1].copy, voiceOut);
  }, [whispers.map((w) => w.alert_id).join(","), voiceOut]); // eslint-disable-line react-hooks/exhaustive-deps

  const ask = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    setBusy(true);
    setInput("");
    setTurns((t) => [...t, { id: ++turnId.current, who: "you", text }]);
    try {
      const tools: string[] = [];
      const result = await answer(text, (entry) => {
        if (entry.tool && !tools.includes(entry.tool)) tools.push(entry.tool);
        setLog((l) => [entry, ...l].slice(0, 40));
      });
      setTurns((t) => [
        ...t,
        {
          id: ++turnId.current,
          who: "alexa",
          text: result.reply,
          intent: result.intent,
          tools,
        },
      ]);
      speak(result.reply, voiceOut);
    } catch (err) {
      const message = `I couldn't reach the household ledger: ${(err as Error).message}`;
      setTurns((t) => [
        ...t,
        { id: ++turnId.current, who: "alexa", text: message, error: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    if (!Ctor) return;
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    const r = new Ctor();
    r.lang = "en-IN";
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      const heard = e.results[0]?.[0]?.transcript ?? "";
      setMicNote(heard ? `Heard: "${heard}"` : "");
      void ask(heard);
    };
    r.onerror = (e) =>
      setMicNote(`Microphone: ${e.error}. Type the request instead.`);
    r.onend = () => setListening(false);
    recognizer.current = r;
    setMicNote("Listening… (browser speech recognition)");
    setListening(true);
    r.start();
  };

  return (
    <section
      className={`panel alexa-panel ${compact ? "compact" : ""}`}
      aria-label="Alexa+"
    >
      <div className="panel-head">
        <h2>
          <AudioLines size={15} aria-hidden /> Alexa+
        </h2>
        <details className="info">
          <summary aria-label="How Alexa+ answers">?</summary>
          <p>
            A deterministic intent router (no LLM) calls the MCP server at{" "}
            <code>/mcp/</code> with your session. Answers come only from tool
            results.
          </p>
        </details>
      </div>
      <div className="alexa-grid">
        <div className="alexa-convo">
          {whispers.length > 0 && (
            <div className="alexa-whispers" aria-label="Whispers">
              {[...whispers].reverse().map((w) => (
                <div
                  className="alexa-whisper"
                  key={w.alert_id}
                  data-kind={w.kind}
                >
                  <strong>
                    {w.kind === "ARRIVAL_ITEM_CHECK"
                      ? "Arrival check"
                      : "T-25 escalation"}
                  </strong>
                  <p>“{w.copy}”</p>
                </div>
              ))}
            </div>
          )}
          <div className="alexa-turns" aria-live="polite" ref={turnsEnd}>
            {turns.length === 0 && (
              <p className="alexa-empty">
                Ask by voice or text. Try one of the examples below.
              </p>
            )}
            {turns.map((t) => (
              <div
                key={t.id}
                className={`alexa-turn ${t.who} ${t.error ? "error" : ""}`}
              >
                <p data-testid={t.who === "alexa" ? "alexa-reply" : undefined}>
                  {t.text}
                </p>
                {t.intent && (
                  <small className="alexa-via">
                    {t.tools?.length ? "answered from " : `intent: ${t.intent}`}
                    {t.tools?.map((name) => (
                      <code key={name}>{name}</code>
                    ))}
                  </small>
                )}
              </div>
            ))}
          </div>
          <div className="alexa-examples">
            {EXAMPLES.map((e) => (
              <button
                type="button"
                className="button"
                key={e}
                disabled={busy}
                onClick={() => void ask(e)}
              >
                {e}
              </button>
            ))}
          </div>
          <form
            className="alexa-input"
            onSubmit={(ev) => {
              ev.preventDefault();
              void ask(input);
            }}
          >
            <input
              aria-label="Ask Alexa+"
              placeholder="Alexa, is my parcel safe?"
              value={input}
              onChange={(ev) => setInput(ev.target.value)}
            />
            <button
              type="button"
              className="button"
              onClick={toggleMic}
              disabled={!Ctor || busy}
              aria-label={listening ? "Stop listening" : "Speak to Alexa+"}
              title={
                Ctor
                  ? "Uses the browser's Web Speech API"
                  : "Speech recognition unavailable in this browser"
              }
            >
              {listening ? <MicOff size={14} /> : <Mic size={14} />}
            </button>
            <button
              type="button"
              className="button"
              onClick={() => {
                setVoiceOut((v) => !v);
                if (voiceOut && "speechSynthesis" in window)
                  window.speechSynthesis.cancel();
              }}
              aria-label={
                voiceOut ? "Mute spoken responses" : "Unmute spoken responses"
              }
            >
              {voiceOut ? <Volume2 size={14} /> : <VolumeX size={14} />}
            </button>
            <button
              type="submit"
              className="button primary"
              disabled={busy || !input.trim()}
            >
              <Send size={13} /> Ask
            </button>
          </form>
          {(micNote || !Ctor) && (
            <p className="alexa-note" role="status">
              {micNote ||
                "Voice input is unavailable in this browser; type instead."}
            </p>
          )}
        </div>
        <aside className="alexa-rail" aria-label="MCP JSON-RPC log">
          <div className="alexa-rail-head">
            <strong>
              <span className="live-dot" aria-hidden /> MCP tool calls
            </strong>
            <span>
              {log.filter((e) => e.tool).length} tool calls · POST /mcp/
            </span>
          </div>
          {log.length === 0 && (
            <p className="alexa-empty">
              Ask a question: each tool the answer needs appears here with its
              arguments and result.
            </p>
          )}
          {log.map((entry, i) => {
            const req = entry.request as RpcBody;
            const args = Object.entries(req.params?.arguments ?? {});
            const rows = resultRows(entry.response);
            return (
              <details
                key={log.length - i}
                className={`alexa-rpc ${entry.tool ? "tool" : "handshake"}`}
                open={i === 0 || (i < 3 && !!entry.tool)}
              >
                <summary>
                  <span
                    className={`rpc-dot ${entry.status < 300 ? "ok" : "bad"}`}
                    title={`HTTP ${entry.status}`}
                    aria-label={`HTTP ${entry.status}`}
                  />
                  {entry.tool ? (
                    <code className="rpc-tool" data-testid="alexa-rpc-tool">
                      {entry.tool}
                    </code>
                  ) : (
                    <strong>{req.method}</strong>
                  )}
                  <time>{entry.ms} ms</time>
                </summary>
                {entry.tool && (
                  <dl className="rpc-io">
                    <dt>args</dt>
                    <dd>
                      {args.length
                        ? args.map(([k, v]) => (
                            <span className="rpc-arg" key={k}>
                              {k}=<b>{short(v)}</b>
                            </span>
                          ))
                        : "none"}
                    </dd>
                    {rows.map(([k, v]) => (
                      <React.Fragment key={k}>
                        <dt>{k}</dt>
                        <dd>{v}</dd>
                      </React.Fragment>
                    ))}
                  </dl>
                )}
                {!entry.tool && rows.length > 0 && (
                  <dl className="rpc-io">
                    {rows.map(([k, v]) => (
                      <React.Fragment key={k}>
                        <dt>{k}</dt>
                        <dd>{v}</dd>
                      </React.Fragment>
                    ))}
                  </dl>
                )}
                <details className="rpc-raw">
                  <summary>Raw JSON-RPC</summary>
                  <pre>{"→ " + JSON.stringify(entry.request, null, 2)}</pre>
                  <pre>{"← " + JSON.stringify(entry.response, null, 2)}</pre>
                </details>
              </details>
            );
          })}
        </aside>
      </div>
      {!compact && (
        <p className="alexa-footnote">
          Web experience calling the Muni MCP server
        </p>
      )}
    </section>
  );
}
