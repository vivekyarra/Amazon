import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  AudioLines,
  Bell,
  Check,
  CheckCheck,
  ChevronRight,
  Circle,
  Clock3,
  Code2,
  Download,
  Eye,
  FileCheck2,
  Fingerprint,
  Home,
  Layers3,
  LockKeyhole,
  LogOut,
  Maximize2,
  Monitor,
  Package,
  Pause,
  Play,
  Plus,
  Radio,
  RotateCcw,
  ScanLine,
  Settings2,
  ShieldCheck,
  Signal,
  Sparkles,
  Terminal,
  Tv,
  Users,
  Video,
  Volume2,
  X,
  Zap,
} from "lucide-react";
import type {
  Contract,
  State,
} from "../../../packages/physical-contract-schema";
import "./style.css";

type Page =
  | "overview"
  | "replay"
  | "contracts"
  | "studio"
  | "incidents"
  | "evidence"
  | "settings";
const labels: Record<Page, string> = {
  overview: "Mission control",
  replay: "Judge replay",
  contracts: "Commitment ledger",
  studio: "Reality-Lock studio",
  incidents: "Evidence & incidents",
  evidence: "Evidence packet",
  settings: "Connections & privacy",
};
const stages = [
  [
    "08:15",
    "Morning promises",
    "Bee stream",
    "Four promises. No reminder prompt.",
  ],
  [
    "14:10",
    "Trust, then verify",
    "Courier deposit",
    "A delivery claim meets physical evidence.",
  ],
  [
    "15:00",
    "A timely intervention",
    "Deadline auditor",
    "Silent at T−60. Context-aware at T−25.",
  ],
  [
    "16:30",
    "Keep a human in the loop",
    "PorchWatchdog",
    "A removal is an observation, not an accusation.",
  ],
  [
    "19:45",
    "The doorway check",
    "Threshold scanner",
    "Not visible doesn’t mean forgotten.",
  ],
  [
    "20:30",
    "Earn your evening",
    "Reality-Lock",
    "Fifteen full movements. Evidence before unlock.",
  ],
];
const icons: Record<string, typeof Package> = {
  drinks: Home,
  sister: Users,
  teacher: Clock3,
  squats: Activity,
  parcel: Package,
};
const fmt = (date: string) =>
  new Date(date).toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
const human = (s: string) => s.toLowerCase().replaceAll("_", " ");
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function api(path: string, body?: unknown) {
  const response = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers:
      body === undefined
        ? {}
        : {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error?.message ?? data.detail?.[0]?.msg ?? "Request failed",
    );
  return data;
}

function App() {
  const [state, setState] = useState<State | null>(null),
    [page, setPage] = useState<Page>(
      ([
        "overview",
        "replay",
        "contracts",
        "studio",
        "incidents",
        "evidence",
        "settings",
      ].includes(new URLSearchParams(location.search).get("page") ?? "")
        ? new URLSearchParams(location.search).get("page")
        : "overview") as Page,
    );
  const [authenticated, setAuthenticated] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [running, setRunning] = useState(false);
  const [branch, setBranch] = useState("unknown"),
    [deposit, setDeposit] = useState("deposit"),
    [arrival, setArrival] = useState("empty"),
    [engagement, setEngagement] = useState("disengaged");
  const [selected, setSelected] = useState<Contract | null>(null),
    [showNotifications, setShowNotifications] = useState(false),
    [password, setPassword] = useState(""),
    [username, setUsername] = useState("demo-admin"),
    [loginBusy, setLoginBusy] = useState(false);
  const [consoleTab, setConsoleTab] = useState<"events" | "decisions" | "mcp">(
    "events",
  );
  const [customUtterance, setCustomUtterance] = useState(""),
    [integrations, setIntegrations] = useState<
      { name: string; status: string; reason: string }[]
    >([]),
    [role, setRole] = useState("admin");
  const [playing, setPlaying] = useState(false),
    [showApproval, setShowApproval] = useState(false),
    [confirmation, setConfirmation] = useState("");
  const stop = useRef(false),
    lastEvent = useRef(0);
  const tv = new URLSearchParams(location.search).has("tv");
  const live = state?.clock_mode === "WALL";
  const [cameraDevices, setCameraDevices] = useState<string[]>([]);
  const [cameraDevice, setCameraDevice] = useState("");
  const [frameTick, setFrameTick] = useState(0);
  const [tvSession, setTvSession] = useState("");
  useEffect(() => {
    if (authenticated && tv)
      void api("/tv/sessions", {})
        .then((d) => setTvSession(d.result.session_id))
        .catch((err) => setError(err.message));
  }, [authenticated, tv]);
  useEffect(() => {
    if (!authenticated || !live) return;
    void api("/camera/devices")
      .then((d) => {
        setCameraDevices(d.devices);
        setCameraDevice((current) => current || d.devices[0] || "");
      })
      .catch((err) => setError(err.message));
    const timer = setInterval(() => {
      if (page === "studio") setFrameTick((t) => t + 1);
      void api("/integrations/status")
        .then((d) => setIntegrations(d.integrations))
        .catch(() => {});
    }, 1000);
    return () => clearInterval(timer);
  }, [authenticated, live, page]);
  const refresh = useCallback(async () => {
    const data = await api("/state");
    setState(data.state);
    setRole(data.role);
    setAuthenticated(true);
    return data.state as State;
  }, []);
  useEffect(() => {
    refresh()
      .catch(() => setAuthenticated(false))
      .finally(() => setLoading(false));
  }, [refresh]);
  useEffect(() => {
    if (!authenticated) return;
    api("/integrations/status").then((d) => setIntegrations(d.integrations));
    const es = new EventSource("/api/events/stream");
    es.addEventListener("ledger", () => {
      lastEvent.current++;
      void refresh();
    });
    es.addEventListener("auth-expired", () => setAuthenticated(false));
    const interval = setInterval(
      () => void refresh().catch(() => setAuthenticated(false)),
      5000,
    );
    return () => {
      es.close();
      clearInterval(interval);
    };
  }, [authenticated, refresh]);
  useEffect(() => {
    if (!tv) return;
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(e.key)) {
        const items = [
          ...document.querySelectorAll<HTMLElement>(
            "button:not(:disabled),a,input,select",
          ),
        ].filter((el) => el.offsetParent !== null);
        const current = items.indexOf(document.activeElement as HTMLElement);
        const next =
          (current +
            (["ArrowDown", "ArrowRight"].includes(e.key) ? 1 : -1) +
            items.length) %
          items.length;
        items[next]?.focus();
        e.preventDefault();
      }
      if (e.key === "Escape" || e.key === "Backspace") {
        setSelected(null);
        setPage("overview");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [tv]);
  const act = async (path: string, body: unknown = {}) => {
    setError("");
    try {
      const d = await api(path, body);
      if (d.state) setState(d.state);
      return d;
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  };
  const guarded = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } catch {
      /* visible error */
    } finally {
      setBusy(false);
    }
  };
  const runStage = async (index: number) => {
    const branches: Record<number, string> = {
      1: "deposit",
      2: deposit,
      3: engagement,
      4: branch,
      5: arrival,
      6: "deposit",
    };
    await act(`/admin/scenarios/${index}/run`, { branch: branches[index] });
  };
  const workout = async () => {
    stop.current = false;
    setPlaying(true);
    try {
      await act("/studio/sessions");
      for (let i = 0; i < 150 && !stop.current; i++) {
        const d = await act("/admin/studio/frame-step");
        if (d.state.studio?.gate === "UNLOCKED") break;
        await sleep(140);
      }
    } catch {
      /* displayed */
    } finally {
      setPlaying(false);
    }
  };
  const fullDay = async () => {
    setRunning(true);
    stop.current = false;
    try {
      await act("/admin/reset");
      for (let i = 1; i <= 6 && !stop.current; i++) {
        await runStage(i);
        await sleep(850);
      }
      if (!stop.current) {
        setPage("studio");
        await workout();
      }
    } catch {
      /* displayed */
    } finally {
      setRunning(false);
    }
  };
  const cancelReplay = () => {
    stop.current = true;
    setRunning(false);
    setPlaying(false);
  };
  const login = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setLoginBusy(true);
    setError("");
    try {
      await api("/auth/login", { username, password });
      await refresh();
      setPassword("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoginBusy(false);
    }
  };
  const logOut = async () => {
    cancelReplay();
    await api("/auth/logout", {});
    setAuthenticated(false);
    setState(null);
  };
  const navigate = (next: Page) => {
    setPage(next);
    setSelected(null);
  };

  if (loading)
    return (
      <div className="loading">
        <Fingerprint size={42} />
        <p>Connecting to the reality ledger…</p>
      </div>
    );
  if (!authenticated)
    return (
      <main className="login">
        <div className="login-story">
          <Brand />
          <div>
            <span className="eyebrow light">EVIDENCE OVER ASSUMPTION</span>
            <h1>
              Life makes promises.
              <br />
              <em>Reality keeps score.</em>
            </h1>
            <p>
              A shared reality ledger for the things you said you’d do.
              <br />
              From the morning conversation to the last verified squat.
            </p>
            <div className="login-pill">
              <ShieldCheck size={16} /> Human judgment. Always in the loop.
            </div>
          </div>
          <small>DONE/IRL · APIs lie. Reality doesn’t.</small>
        </div>
        <div className="login-form">
          <div className="login-mark">
            <Fingerprint size={38} />
          </div>
          <span className="eyebrow">YOUR REALITY, CONNECTED</span>
          <h2>Welcome to mission control.</h2>
          <p>Sign in to your private DONE/IRL workspace.</p>
          <form onSubmit={login}>
            <label>
              Workspace account
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                placeholder="Your local access password"
              />
            </label>
            {error && (
              <div role="alert" className="error-inline">
                {error}
              </div>
            )}
            <button className="button primary" disabled={loginBusy}>
              {loginBusy ? "Connecting…" : "Open mission control"}
              <ArrowRight size={16} />
            </button>
          </form>
          <div className="login-note">
            <LockKeyhole size={17} />
            <p>
              Local access is generated during setup.
              <br />
              Run <code>./scripts/access.sh</code> in your private terminal.
              <br />
              No Amazon credentials needed for replay.
            </p>
          </div>
        </div>
      </main>
    );
  if (!state) return null;
  const verified = state.contracts.filter(
    (c) => c.status === "VERIFIED",
  ).length;
  const active = state.contracts.filter(
    (c) => !["VERIFIED", "CANCELLED", "REJECTED"].includes(c.status),
  ).length;
  const currentStage = stages[Math.max(0, state.scenario - 1)];
  const incident = state.incidents[0];
  const latestImage = [...state.evidence]
    .reverse()
    .find((v) => v.mime === "image/png" && v.kind !== "PERSON_CROP");
  const eventList = [...state.events]
    .reverse()
    .filter(
      (ev) =>
        consoleTab !== "decisions" ||
        /verified|evaluated|mismatch|authorized|consent|gap/.test(
          ev.event_type,
        ),
    );
  const studio = state.studio;
  const reset = () =>
    guarded(async () => {
      cancelReplay();
      await act("/admin/reset");
    });
  const openStudio = () =>
    guarded(async () => {
      if (live) {
        await api("/camera/start", { device_id: cameraDevice });
        await refresh();
      } else {
        if (!state.contracts.length) await runStage(1);
        await act("/studio/sessions");
      }
      navigate("studio");
    });
  const incidentAction = (
    action: string,
    extra: Record<string, unknown> = {},
  ) =>
    guarded(async () => {
      await act(`/incidents/${incident.incident_id}/${action}`, {
        action,
        revision: incident.revision,
        ...extra,
      });
      setShowApproval(false);
      setConfirmation("");
    });
  const goContract = (c: Contract) => {
    setSelected(c);
    setPage("contracts");
  };

  return (
    <div className={`app ${tv ? "tv-mode" : ""}`}>
      <aside className="sidebar">
        <Brand />
        <div className="workspace">
          <span className="workspace-avatar">D</span>
          <div>
            <strong>{live ? "Your household" : "Demo household"}</strong>
            <small>Private workspace</small>
          </div>
          <span className="workspace-dot" />
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav>
          {(
            [
              ["overview", Home],
              ["replay", Layers3],
              ["contracts", CheckCheck],
              ["studio", ScanLine],
              ["incidents", ShieldCheck],
            ] as const
          ).map(([id, Icon]) => (
            <button
              key={id}
              className={`nav-item ${page === id ? "active" : ""}`}
              onClick={() => navigate(id)}
            >
              <Icon size={18} />
              <span>{labels[id]}</span>
              {id === "incidents" && incident && (
                <span className="nav-count">1</span>
              )}
              {id === "replay" && <span className="nav-small">DEMO</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connected-note">
            <span className="pulse-dot" />
            <div>
              <strong>Reality ledger online</strong>
              <small>Persistent · SQLite WAL</small>
            </div>
            <Signal size={16} />
          </div>
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings2 size={18} />
            Connections & privacy
          </button>
          <div className="profile">
            <span className="avatar">{role === "admin" ? "JD" : "OW"}</span>
            <div>
              <strong>
                {role === "admin" ? "Judge workspace" : "Household owner"}
              </strong>
              <small>
                {role === "admin"
                  ? "Replay administrator"
                  : "Private household"}
              </small>
            </div>
            <button
              className="icon-button"
              title="Sign out"
              onClick={() => void logOut()}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            Workspace
            <ChevronRight size={14} />
            <strong>{labels[page]}</strong>
          </div>
          <div className="topbar-right">
            <span className="source-tag">
              <span />
              {live ? "PRIVATE HOUSEHOLD" : "SYNTHETIC DEMO"}
            </span>
            <span className="clock">
              <Clock3 size={15} />
              {fmt(state.now)} IST
            </span>
            <button
              className="icon-button notification-button"
              aria-label="Open notifications"
              onClick={() => setShowNotifications(!showNotifications)}
            >
              <Bell size={19} />
              {state.alerts.length > 0 && <i />}
            </button>
            {tvSession && (
              <span
                className="studio-source"
                title="Authenticated session; device runtime proof is separate"
              >
                TV session {tvSession.slice(-8)}
              </span>
            )}
            <span className="avatar small">{live ? "OW" : "JD"}</span>
          </div>
        </header>
        <main className="content">
          {tv && (
            <div className="tv-navigation">
              {(["overview", "contracts", "incidents", "studio"] as Page[]).map(
                (id) => (
                  <button
                    key={id}
                    className="button"
                    onClick={() => navigate(id)}
                  >
                    {labels[id]}
                  </button>
                ),
              )}
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">TUESDAY, 20 OCTOBER · VIRTUAL DAY</div>
              <h1>
                {labels[page]}
                <span className="heading-dot">.</span>
              </h1>
              <p>
                {page === "overview"
                  ? "A little less remembering. A lot more knowing."
                  : page === "replay"
                    ? "One connected day. Six moments where reality matters."
                    : page === "studio"
                      ? "A promise to yourself, backed by movement."
                      : page === "incidents"
                        ? "Preserve what happened. You decide what happens next."
                        : page === "settings"
                          ? "Know what’s connected. Control what’s collected."
                          : "Every promise has a story. Every closure needs evidence."}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="button"
                onClick={() => window.open("/?tv=1", "_blank", "noopener")}
              >
                <Tv size={16} />
                TV preview
                <ArrowRight size={14} />
              </button>
              <a className="button" href="/api/export" download>
                <Download size={16} />
                Export evidence
              </a>
            </div>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {!state.consent && (
            <div className="warning-banner">
              <Pause size={16} />
              Collection paused. Watchdogs and camera processing require
              consent.
              <button
                onClick={() =>
                  void guarded(() => act("/consent", { enabled: true }))
                }
              >
                Restore demo consent
              </button>
            </div>
          )}
          {(page === "overview" || page === "replay") && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <div className="hero-kicker">
                    <span className="pulse-dot" />
                    THE REALITY LAYER FOR YOUR DAY
                  </div>
                  <h2>
                    Said is a start.
                    <br />
                    <span>Verified is done.</span>
                  </h2>
                  <p>
                    Your commitments, connected to the world.
                    <br />
                    Not another reminder. A reason to trust the outcome.
                  </p>
                  <div className="hero-buttons">
                    <button
                      className="button mint"
                      disabled={running || busy || role !== "admin"}
                      onClick={() => void fullDay()}
                    >
                      <Play size={15} fill="currentColor" />
                      {running ? "Replaying the day…" : "Run the full day"}
                      <ArrowRight size={16} />
                    </button>
                    <button
                      className="hero-link"
                      onClick={() => navigate("replay")}
                    >
                      Explore the replay
                      <ChevronRight size={15} />
                    </button>
                  </div>
                  <div className="hero-foot">
                    <ShieldCheck size={13} />
                    Synthetic sources. Real state transitions. Always labeled.
                  </div>
                </div>
                <div className="reality-visual">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <div className="orbit orbit-three" />
                  <div className="center-orb">
                    <Fingerprint size={52} />
                    <span>REALITY ENGINE</span>
                    <small>Evidence → confidence → closure</small>
                  </div>
                  <div className="orbit-node node-bee">
                    <AudioLines size={18} />
                    <div>
                      <strong>Bee</strong>
                      <small>Conversation context</small>
                    </div>
                    <i />
                  </div>
                  <div className="orbit-node node-ring">
                    <Video size={18} />
                    <div>
                      <strong>Ring</strong>
                      <small>Physical observation</small>
                    </div>
                    <i />
                  </div>
                  <div className="orbit-node node-tv">
                    <Tv size={18} />
                    <div>
                      <strong>Fire TV</strong>
                      <small>Verified action</small>
                    </div>
                    <i />
                  </div>
                  <span className="visual-label">SIMULATED CONNECTIONS</span>
                </div>
              </section>
              <div className="stats-grid">
                <Stat
                  icon={CheckCheck}
                  label="COMMITMENTS"
                  value={state.contracts.length.toString().padStart(2, "0")}
                  detail={`${active} still in progress`}
                  color="mint"
                />
                <Stat
                  icon={ShieldCheck}
                  label="VERIFIED BY EVIDENCE"
                  value={verified.toString().padStart(2, "0")}
                  detail="No reminder counts as done"
                  color="blue"
                />
                <Stat
                  icon={Eye}
                  label="PERSISTENT WATCHDOGS"
                  value={state.subagents
                    .filter((a) => a.status === "WATCHING")
                    .length.toString()
                    .padStart(2, "0")}
                  detail="Event-driven, not always recording"
                  color="purple"
                />
                <Stat
                  icon={Fingerprint}
                  label="EVIDENCE COLLECTED"
                  value={state.evidence.length.toString().padStart(2, "0")}
                  detail="SHA-256 integrity protected"
                  color="amber"
                />
              </div>
              <section className="replay-section">
                <div className="section-title">
                  <div>
                    <span className="eyebrow">THE CANONICAL DAY</span>
                    <h2>Six moments. One connected story.</h2>
                  </div>
                  <div className="replay-controls">
                    {(running || playing) && (
                      <button className="button" onClick={cancelReplay}>
                        <Pause size={14} />
                        Pause
                      </button>
                    )}
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={reset}
                    >
                      <RotateCcw size={14} />
                      Reset day
                    </button>
                    <span className="tiny-tag">JUDGE MODE</span>
                  </div>
                </div>
                <div className="stage-grid">
                  {stages.map(([time, title, source, description], i) => {
                    const Icon = [
                      AudioLines,
                      Package,
                      Clock3,
                      ShieldCheck,
                      Home,
                      Activity,
                    ][i];
                    const done = state.scenario > i;
                    return (
                      <button
                        className={`stage-card ${state.scenario === i + 1 ? "current" : ""} ${done ? "started" : ""}`}
                        key={time}
                        disabled={busy || running || role !== "admin"}
                        onClick={() => void guarded(() => runStage(i + 1))}
                        aria-label={`${i + 1}. ${time} ${title}`}
                      >
                        <div className="stage-top">
                          <span className="stage-index">0{i + 1}</span>
                          <span>{time}</span>
                          {done ? (
                            <Check size={13} />
                          ) : (
                            <ArrowRight size={13} />
                          )}
                        </div>
                        <div className="stage-icon">
                          <Icon size={21} />
                        </div>
                        <h3>{title}</h3>
                        <p>{description}</p>
                        <div className="stage-source">
                          {source}
                          <ChevronRight size={12} />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
              {page === "replay" && (
                <section className="panel replay-options">
                  <div>
                    <span className="eyebrow">EXPLICIT SCENARIO FORKS</span>
                    <h3>Change the story, keep the truth.</h3>
                    <p>Reset before changing a branch already played.</p>
                  </div>
                  <label>
                    Courier
                    <select
                      aria-label="Courier"
                      value={deposit}
                      onChange={(e) => setDeposit(e.target.value)}
                    >
                      <option value="deposit">Real deposit</option>
                      <option value="fake">Courier fake-out</option>
                    </select>
                  </label>
                  <label>
                    Removal
                    <select
                      aria-label="Removal"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                    >
                      <option value="unknown">Unknown person</option>
                      <option value="family">Authorized family pickup</option>
                      <option value="retained">Parcel remains</option>
                    </select>
                  </label>
                  <label>
                    Meeting context
                    <select
                      aria-label="Meeting context"
                      value={engagement}
                      onChange={(e) => setEngagement(e.target.value)}
                    >
                      <option value="disengaged">
                        Preparation unconfirmed
                      </option>
                      <option value="engaged">Actively preparing</option>
                    </select>
                  </label>
                  <label>
                    Arrival
                    <select
                      aria-label="Arrival"
                      value={arrival}
                      onChange={(e) => setArrival(e.target.value)}
                    >
                      <option value="empty">Drinks not visible</option>
                      <option value="visible">Drinks visible</option>
                      <option value="ambiguous">Occluded / ambiguous</option>
                    </select>
                  </label>
                </section>
              )}
              <div className="overview-bottom">
                <section className="panel commitments-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Your commitment ledger</h2>
                      <p>
                        Promises stay open until the evidence says otherwise.
                      </p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("contracts")}
                    >
                      View all
                      <ArrowRight size={14} />
                    </button>
                  </div>
                  {state.contracts.length ? (
                    state.contracts.map((c) => (
                      <ContractRow
                        key={c.contract_id}
                        c={c}
                        onClick={() => goContract(c)}
                      />
                    ))
                  ) : (
                    <div className="empty-state">
                      <div className="empty-icon">
                        <AudioLines size={25} />
                      </div>
                      <h3>Every promise starts somewhere.</h3>
                      <p>
                        Start the morning replay to hear the household’s
                        <br />
                        four commitments become durable contracts.
                      </p>
                      <button
                        className="text-button"
                        onClick={() => void guarded(() => runStage(1))}
                      >
                        Play morning promises
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  )}
                  <div className="panel-footer">
                    <LockKeyhole size={12} /> Private to your household. Never
                    verified by a reminder.
                  </div>
                </section>
                <section className="panel live-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Inside the reality engine</h2>
                      <p>Input → verification → durable state</p>
                    </div>
                    <span className="live-badge">
                      <span />
                      LIVE LEDGER
                    </span>
                  </div>
                  <div className="engine-status">
                    <div className="engine-status-icon">
                      <Radio size={20} />
                    </div>
                    <div>
                      <strong>
                        {state.events.length
                          ? currentStage[1]
                          : "Ready when you are"}
                      </strong>
                      <small>
                        {state.events.length
                          ? `${fmt(state.now)} · Scenario ${state.scenario}/6`
                          : "Waiting for the first consented event"}
                      </small>
                    </div>
                    <Activity size={18} />
                  </div>
                  <div className="compact-events">
                    {state.events.length ? (
                      [...state.events]
                        .reverse()
                        .slice(0, 4)
                        .map((ev) => (
                          <div className="compact-event" key={ev.event_id}>
                            <span
                              className={`event-dot ${ev.event_type.includes("verified") ? "verified" : ""}`}
                            />
                            <div>
                              <strong>
                                {human(ev.event_type.replaceAll(".", " · "))}
                              </strong>
                              <small>
                                {ev.event_id} · {ev.trace_id}
                              </small>
                            </div>
                            <time>{fmt(ev.occurred_at)}</time>
                          </div>
                        ))
                    ) : (
                      <>
                        <div className="pipeline-step">
                          <AudioLines size={17} />
                          <div>
                            <strong>Listen with consent</strong>
                            <small>
                              Understand the promise and its context
                            </small>
                          </div>
                          <span>01</span>
                        </div>
                        <div className="pipeline-step">
                          <Eye size={17} />
                          <div>
                            <strong>Observe with purpose</strong>
                            <small>
                              Look for relevant, authorized evidence
                            </small>
                          </div>
                          <span>02</span>
                        </div>
                        <div className="pipeline-step">
                          <ShieldCheck size={17} />
                          <div>
                            <strong>Close with confidence</strong>
                            <small>
                              Keep uncertainty visible, humans in control
                            </small>
                          </div>
                          <span>03</span>
                        </div>
                      </>
                    )}
                  </div>
                  <button
                    className="panel-link"
                    onClick={() => navigate("replay")}
                  >
                    <Terminal size={14} />
                    Open event & decision stream
                    <ArrowRight size={14} />
                  </button>
                </section>
              </div>
            </>
          )}
          {page === "replay" && (
            <>
              <section className="panel replay-toolbar">
                <span>
                  <Clock3 size={16} />
                  {fmt(state.now)} virtual time
                </span>
                <button
                  className="button"
                  onClick={() =>
                    void guarded(() =>
                      act("/admin/clock/advance", { minutes: 25 }),
                    )
                  }
                >
                  Advance 25 minutes
                </button>
                <button
                  className="button"
                  onClick={() => void guarded(() => act("/admin/sister-proof"))}
                >
                  Inject sister call proof
                </button>
                <button
                  className="button"
                  onClick={() => void guarded(() => act("/admin/owner-pickup"))}
                >
                  Observe owner pickup
                </button>
                <select
                  aria-label="Failure injection"
                  defaultValue=""
                  onChange={(ev) => {
                    if (ev.target.value)
                      void guarded(() =>
                        act("/admin/failures/" + ev.target.value),
                      );
                    ev.target.value = "";
                  }}
                >
                  <option value="" disabled>
                    Inject a failure…
                  </option>
                  <option value="camera-offline">Camera offline</option>
                  <option value="token-expired">Token expired</option>
                  <option value="storage-unavailable">
                    Storage unavailable
                  </option>
                  <option value="clear">Clear injected failures</option>
                </select>
              </section>
              <div className="replay-workbench">
                <section className="panel camera-panel">
                  <div className="panel-heading">
                    <h2>Source observation</h2>
                    <span className="tiny-tag">SYNTHETIC PIXELS</span>
                  </div>
                  {latestImage ? (
                    <img
                      src={"/api/evidence/" + latestImage.evidence_id}
                      alt="Calibrated synthetic porch observation"
                    />
                  ) : (
                    <div className="camera-empty">
                      <Video size={36} />
                      <p>
                        Run a camera scenario to inspect its actual processed
                        frame.
                      </p>
                    </div>
                  )}
                  <div className="camera-caption">
                    <span>Calibrated marker detector · v1</span>
                    <span>No live Ring feed</span>
                  </div>
                </section>
                <section className="panel event-panel">
                  <div className="tabs">
                    {(["events", "decisions", "mcp"] as const).map((tab) => (
                      <button
                        className={consoleTab === tab ? "active" : ""}
                        onClick={() => setConsoleTab(tab)}
                        key={tab}
                      >
                        {tab === "mcp"
                          ? "MCP inspector"
                          : tab === "events"
                            ? "Event stream"
                            : "Verification decisions"}
                      </button>
                    ))}
                    <span>{state.events.length} EVENTS</span>
                  </div>
                  {consoleTab === "mcp" ? (
                    <div className="mcp-inspector">
                      <Code2 size={26} />
                      <h3>One protocol. Shared truth.</h3>
                      <p>
                        The official MCP SDK serves Streamable HTTP at{" "}
                        <code>/mcp/</code>. Tool calls use this same ledger. A
                        protocol test uses an external SDK client.
                      </p>
                      <pre>
                        {JSON.stringify(
                          { jsonrpc: "2.0", method: "tools/list", id: 1 },
                          null,
                          2,
                        )}
                      </pre>
                      <p>
                        Scenario buttons invoke REST event ingestion; these are
                        not fabricated MCP calls.
                      </p>
                    </div>
                  ) : (
                    <div className="event-scroll">
                      {eventList.length ? (
                        eventList.map((ev) => (
                          <details key={ev.event_id}>
                            <summary>
                              <span className="event-dot" />
                              <time>{fmt(ev.occurred_at)}</time>
                              <strong>{ev.event_type}</strong>
                              <span>{ev.event_id}</span>
                            </summary>
                            <pre>{JSON.stringify(ev, null, 2)}</pre>
                          </details>
                        ))
                      ) : (
                        <div className="empty-state">
                          <Terminal size={24} />
                          <p>No matching events yet.</p>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              </div>
            </>
          )}
          {page === "contracts" && (
            <div className="ledger-layout">
              <section className="panel">
                <div className="panel-heading">
                  <h2>
                    All commitments{" "}
                    <span className="count-badge">
                      {state.contracts.length}
                    </span>
                  </h2>
                  <span className="tiny-tag">SHARED STATE</span>
                </div>
                {state.contracts.map((c) => (
                  <ContractRow
                    key={c.contract_id}
                    c={c}
                    onClick={() => setSelected(c)}
                  />
                ))}
                {!state.contracts.length && (
                  <div className="empty-state">
                    <CheckCheck size={28} />
                    <h3>Your ledger is clear.</h3>
                    <p>Run the morning scenario to compile four promises.</p>
                    <button
                      className="button primary"
                      onClick={() => void guarded(() => runStage(1))}
                    >
                      Start the morning
                      <Play size={14} />
                    </button>
                  </div>
                )}
                <div className="custom-ingest">
                  <h3>A new promise, in your own words.</h3>
                  <p>
                    Try “I’ll call my sister before 7 PM.” Synthetic input uses
                    the same compiler.
                  </p>
                  <form
                    onSubmit={(ev) => {
                      ev.preventDefault();
                      void guarded(async () => {
                        await act("/ingest/bee-simulated", {
                          event_id: crypto.randomUUID(),
                          utterance: customUtterance,
                          speaker: "SELF",
                          counterparty: "Household",
                          occurred_at: state.now,
                          timezone: "Asia/Kolkata",
                        });
                        setCustomUtterance("");
                      });
                    }}
                  >
                    <input
                      value={customUtterance}
                      onChange={(ev) => setCustomUtterance(ev.target.value)}
                      placeholder="I’ll…"
                      required
                      maxLength={4000}
                    />
                    <button
                      className="button primary"
                      disabled={role !== "admin" || busy}
                    >
                      <Plus size={16} />
                      Compile
                    </button>
                  </form>
                </div>
              </section>
              <section className="panel detail-panel">
                {selected ? (
                  (() => {
                    const c =
                      state.contracts.find(
                        (c) => c.contract_id === selected.contract_id,
                      ) ?? selected;
                    const Icon = icons[c.key] ?? CheckCheck;
                    return (
                      <>
                        <div className="detail-icon">
                          <Icon size={27} />
                        </div>
                        <span className="eyebrow">PHYSICAL STATE CONTRACT</span>
                        <h2>{c.title}</h2>
                        <Status status={c.status} />
                        <blockquote>“{c.original_utterance}”</blockquote>
                        <dl>
                          <dt>Counterparty</dt>
                          <dd>{c.counterparty.label}</dd>
                          <dt>Due / trigger</dt>
                          <dd>
                            {c.due_at
                              ? fmt(c.due_at) + " IST"
                              : human(c.deadline_trigger ?? "On evidence")}
                          </dd>
                          <dt>Verification policy</dt>
                          <dd>{human(c.verification_modality)}</dd>
                          <dt>Evidence</dt>
                          <dd>{c.evidence_ids.length} linked record(s)</dd>
                          <dt>Source</dt>
                          <dd>{human(c.source_mode)}</dd>
                          <dt>Revision</dt>
                          <dd>{c.revision}</dd>
                        </dl>
                        {c.custody_status && (
                          <div className="info-box">
                            Custody: {human(c.custody_status)}
                          </div>
                        )}
                        {c.visibility && (
                          <div className="info-box">
                            Visibility: {human(c.visibility)}. A supporting
                            observation is not final closure.
                          </div>
                        )}
                        <h3>Durable schedule</h3>
                        {c.scheduled_jobs.length ? (
                          c.scheduled_jobs.map((j) => (
                            <div className="schedule-row" key={j.kind}>
                              <Clock3 size={14} />
                              <strong>{j.kind}</strong>
                              <time>{fmt(j.at)}</time>
                              <small>{human(j.status)}</small>
                            </div>
                          ))
                        ) : (
                          <p className="muted">
                            Waiting for a physical trigger.
                          </p>
                        )}
                        <div className="detail-actions">
                          {c.status === "NEEDS_CONFIRMATION" && (
                            <>
                              <button
                                className="button primary"
                                onClick={() =>
                                  void guarded(() =>
                                    act(`/contracts/${c.contract_id}/confirm`, {
                                      action: "accept",
                                      revision: c.revision,
                                    }),
                                  )
                                }
                              >
                                Accept promise
                              </button>
                              <button
                                className="button"
                                onClick={() =>
                                  void guarded(() =>
                                    act(`/contracts/${c.contract_id}/confirm`, {
                                      action: "reject",
                                      revision: c.revision,
                                    }),
                                  )
                                }
                              >
                                Reject
                              </button>
                            </>
                          )}
                          {c.key === "drinks" && c.status !== "VERIFIED" && (
                            <button
                              className="button"
                              onClick={() =>
                                void guarded(() =>
                                  act(`/contracts/${c.contract_id}/confirm`, {
                                    action: "confirm-drinks",
                                    revision: c.revision,
                                  }),
                                )
                              }
                            >
                              Confirm I have the drinks <Check size={14} />
                            </button>
                          )}
                          {!["VERIFIED", "CANCELLED", "REJECTED"].includes(
                            c.status,
                          ) && (
                            <button
                              className="text-button"
                              onClick={() =>
                                void guarded(() =>
                                  act(`/contracts/${c.contract_id}/confirm`, {
                                    action: "cancel",
                                    revision: c.revision,
                                  }),
                                )
                              }
                            >
                              Cancel commitment
                            </button>
                          )}
                        </div>
                      </>
                    );
                  })()
                ) : (
                  <div className="empty-state">
                    <Fingerprint size={35} />
                    <h3>Look a little closer.</h3>
                    <p>
                      Select a commitment to inspect its origin,
                      <br />
                      evidence policy, and durable schedule.
                    </p>
                  </div>
                )}
              </section>
            </div>
          )}
          {page === "studio" && (
            <>
              <div className="studio-layout">
                <section className="studio-screen">
                  <div className="studio-screen-top">
                    <span>
                      <span className="pulse-dot" />
                      {studio?.status === "RUNNING"
                        ? live
                          ? "PROCESSING RING FRAMES"
                          : "PROCESSING SYNTHETIC FRAMES"
                        : "CAMERA STUDIO"}
                    </span>
                    <span className="studio-source">
                      {live
                        ? studio?.source_mode === "LIVE_VERIFIED" &&
                          studio?.status === "RUNNING"
                          ? "LIVE RING"
                          : "AWAITING LIVE CAMERA"
                        : "DEMO / SYNTHETIC"}
                    </span>
                  </div>
                  {studio ? (
                    <img
                      className="pose-feed"
                      src={
                        live
                          ? `/api/camera/frame?v=${frameTick}`
                          : `/api/studio/frame?v=${studio.fixture_frame_index ?? 0}-${studio.angle}`
                      }
                      alt={
                        live
                          ? "Authorized Ring frames with MediaPipe skeleton"
                          : "Synthetic marker pose extraction with skeleton overlay"
                      }
                    />
                  ) : (
                    <div className="studio-intro">
                      <div className="studio-intro-icon">
                        <ScanLine size={60} />
                      </div>
                      <h2>
                        Your living room.
                        <br />
                        Your proof.
                      </h2>
                      <p>
                        Connect the promise to a complete movement.
                        <br />
                        {live
                          ? "Choose a linked Ring camera. MediaPipe evaluates complete movements."
                          : "This replay processes generated marker frames. Live Ring and human pose are not connected."}
                      </p>
                      {live && (
                        <label>
                          Linked camera
                          <select
                            value={cameraDevice}
                            onChange={(event) =>
                              setCameraDevice(event.target.value)
                            }
                          >
                            <option value="">
                              Choose an authorized camera
                            </option>
                            {cameraDevices.map((device) => (
                              <option key={device} value={device}>
                                {device}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      <button
                        className="button mint"
                        onClick={openStudio}
                        disabled={live && !cameraDevice}
                      >
                        <Video size={16} />
                        {live ? "Connect Ring camera" : "Open synthetic camera"}
                      </button>
                    </div>
                  )}
                  <div className="studio-screen-bottom">
                    <span>
                      <LockKeyhole size={15} />
                      {studio?.gate === "UNLOCKED"
                        ? "IN-APP ENTERTAINMENT READY"
                        : studio?.gate === "USER_OVERRIDE"
                          ? "ACCESSIBLE USER OVERRIDE"
                          : "IN-APP REALITY-LOCK"}
                    </span>
                    <span>
                      {studio?.quality
                        ? human(studio.quality)
                        : "Awaiting consented source"}
                    </span>
                  </div>
                </section>
                <aside className="panel workout-panel">
                  <div className="eyebrow">A PROMISE TO YOURSELF</div>
                  <h2>
                    Show up.
                    <br />
                    Squat down.
                  </h2>
                  <p>
                    Fifteen complete cycles before your evening entertainment.
                    Your pace. Your choice.
                  </p>
                  <div
                    className={`rep-ring ${studio?.gate === "UNLOCKED" ? "unlocked" : ""}`}
                    style={
                      {
                        "--progress": `${((studio?.count ?? 0) / 15) * 100}%`,
                      } as React.CSSProperties
                    }
                  >
                    <div>
                      <strong>
                        {(studio?.count ?? 0).toString().padStart(2, "0")}
                      </strong>
                      <span>/ 15 VERIFIED CYCLES</span>
                    </div>
                  </div>
                  <div className="workout-metrics">
                    <div>
                      <small>KNEE ANGLE</small>
                      <strong>
                        {studio?.angle ?? "—"}
                        {studio ? "°" : ""}
                      </strong>
                    </div>
                    <div>
                      <small>PHASE</small>
                      <strong>{human(studio?.phase ?? "Not started")}</strong>
                    </div>
                  </div>
                  {studio?.gate === "UNLOCKED" ? (
                    <div className="success-box">
                      <ShieldCheck size={22} />
                      <div>
                        <strong>Promise kept. Evidence saved.</strong>
                        <p>
                          {live
                            ? "15 camera-backed cycles verified."
                            : "15 synthetic cycles verified."}{" "}
                          In-app gate unlocked.
                        </p>
                      </div>
                    </div>
                  ) : live ? (
                    <div className="info-box">
                      <p>
                        Live camera verification runs on the server. Reconnect
                        after the permitted Ring session ends; your verified
                        count is preserved.
                      </p>
                      <button
                        className="button primary wide"
                        onClick={openStudio}
                        disabled={busy || !cameraDevice}
                      >
                        Connect camera
                      </button>
                      <button
                        className="button wide"
                        onClick={() =>
                          void guarded(async () => {
                            await api("/camera/stop", {});
                            await refresh();
                          })
                        }
                      >
                        Close camera
                      </button>
                    </div>
                  ) : (
                    <button
                      className="button primary wide"
                      disabled={playing || busy || role !== "admin"}
                      onClick={() => void workout()}
                    >
                      <Play size={15} />
                      {playing
                        ? "Processing marker frames…"
                        : "Run synthetic workout"}
                    </button>
                  )}
                  {playing && (
                    <button className="button wide" onClick={cancelReplay}>
                      <Pause size={15} />
                      Pause replay
                    </button>
                  )}
                  {studio && studio.status !== "COMPLETED" && (
                    <div className="workout-secondary">
                      <button
                        className="text-button"
                        onClick={() =>
                          void guarded(() =>
                            act("/studio/control", {
                              action:
                                studio.status === "PAUSED" ? "resume" : "pause",
                            }),
                          )
                        }
                      >
                        {studio.status === "PAUSED"
                          ? "Resume session"
                          : "Pause session"}
                      </button>
                      <button
                        className="text-button"
                        onClick={() =>
                          void guarded(() =>
                            act("/studio/control", {
                              action: "accessible-override",
                            }),
                          )
                        }
                      >
                        Use accessible override
                      </button>
                    </div>
                  )}
                  <p className="workout-disclaimer">
                    This is voluntary movement recognition, not medical
                    guidance. Override opens the in-app gate and keeps the
                    physical promise unverified. No other apps are locked.
                  </p>
                </aside>
              </div>
              <div className="studio-note">
                <ShieldCheck size={20} />
                <div>
                  <strong>Proof, with an honest boundary.</strong>
                  <p>
                    Marker pixels are decoded into landmarks and checked for
                    full cycles. Live human pose needs the optional MediaPipe
                    worker, a calibrated camera, and device validation. This
                    screen is a web preview, not Fire TV runtime proof.
                  </p>
                </div>
              </div>
            </>
          )}
          {page === "incidents" && (
            <>
              {incident ? (
                <div className="incident-layout">
                  <section className="panel incident-main">
                    <div className="panel-heading">
                      <div>
                        <span className="eyebrow">HUMAN REVIEW REQUIRED</span>
                        <h2>A package moved. Was it authorized?</h2>
                      </div>
                      <Status status={incident.status} />
                    </div>
                    <div className="incident-image">
                      <img
                        src={
                          "/api/evidence/" + incident.packet.removal_evidence_id
                        }
                        alt="Synthetic removal evidence"
                      />
                      <span>
                        DEMO / SYNTHETIC · {fmt(incident.detected_at)} IST
                      </span>
                    </div>
                    {incident.packet.source_clip_evidence_id && (
                      <div className="incident-video">
                        <video
                          controls
                          preload="metadata"
                          aria-label="15-second synthetic removal clip"
                          src={
                            "/api/evidence/" +
                            incident.packet.source_clip_evidence_id
                          }
                        />
                        <p>
                          15-second generated source clip · DEMO / SYNTHETIC ·
                          no live Ring recording
                        </p>
                      </div>
                    )}
                    <div className="incident-copy">
                      <h3>Observation, without accusation.</h3>
                      <p>
                        The tracked parcel moved from the porch toward the
                        street. We cannot infer identity or intent. The person
                        crop below is a synthetic marker, never a facial
                        identity match.
                      </p>
                      <div className="quality-notice">
                        <Video size={19} />
                        <div>
                          <strong>
                            {incident.clip_actual_duration_seconds
                              ? "Synthetic video preserved"
                              : "Evidence incomplete"}
                          </strong>
                          <p>
                            {incident.clip_actual_duration_seconds}s clip
                            available. Synthetic source and annotated artifacts
                            are preserved. No live Ring recording is claimed.
                          </p>
                        </div>
                      </div>
                      <div className="incident-actions">
                        {[
                          "AWAITING_HUMAN_DECISION",
                          "EVIDENCE_PREPARED",
                        ].includes(incident.status) && (
                          <button
                            className="button primary"
                            onClick={() => incidentAction("authorize-pickup")}
                          >
                            <Users size={16} />
                            Confirm authorized pickup
                          </button>
                        )}
                        {incident.status === "AWAITING_HUMAN_DECISION" && (
                          <button
                            className="button"
                            onClick={() => incidentAction("prepare-report")}
                          >
                            <FileCheck2 size={16} />
                            Review evidence / Prepare report
                          </button>
                        )}
                        {incident.status === "EVIDENCE_PREPARED" && (
                          <button
                            className="button"
                            onClick={() => setShowApproval(true)}
                          >
                            Review simulated report approval
                            <ArrowRight size={15} />
                          </button>
                        )}
                        {incident.status === "REPORT_APPROVED" && (
                          <button
                            className="button primary"
                            onClick={() => incidentAction("dispatch-report")}
                          >
                            Send to demo receiver only
                          </button>
                        )}
                        {["EVIDENCE_PREPARED", "REPORT_APPROVED"].includes(
                          incident.status,
                        ) && (
                          <button
                            className="text-button"
                            onClick={() => incidentAction("cancel-report")}
                          >
                            Cancel report review
                          </button>
                        )}
                      </div>
                      {incident.receipt && (
                        <div className="warning-banner">
                          {incident.receipt.label}
                          <br />
                          {incident.receipt.receipt_id}
                        </div>
                      )}
                    </div>
                  </section>
                  <section className="panel evidence-panel">
                    <div className="panel-heading">
                      <h2>Evidence packet</h2>
                      <Fingerprint size={18} />
                    </div>
                    <div className="evidence-content">
                      <div className="person-crop">
                        <img
                          src={
                            "/api/evidence/" +
                            incident.packet.person_crop_evidence_id
                          }
                          alt="Synthetic person marker crop"
                        />
                        <div>
                          <strong>Best available person crop</strong>
                          <small>Synthetic · no facial identification</small>
                        </div>
                      </div>
                      <dl>
                        <dt>Detected</dt>
                        <dd>{fmt(incident.detected_at)} IST · virtual time</dd>
                        <dt>Location</dt>
                        <dd>Synthetic porch · no real address</dd>
                        <dt>Source</dt>
                        <dd>Calibrated generated pixels</dd>
                        <dt>Coverage</dt>
                        <dd>
                          {incident.clip_actual_duration_seconds}-second
                          synthetic clip
                        </dd>
                        <dt>Receiver</dt>
                        <dd>DEMO_RECEIVER_ONLY</dd>
                        <dt>Official dispatches</dt>
                        <dd>0 · export / simulated dispatch only</dd>
                      </dl>
                      <span className="eyebrow">SHA-256 MANIFEST</span>
                      <code className="hash">{incident.manifest_hash}</code>
                      <p className="muted">
                        A digest detects tampering. It does not establish legal
                        admissibility.
                      </p>
                      <a className="button wide" href="/api/export" download>
                        <Download size={16} />
                        Export verified manifest
                      </a>
                      <h3>Linked evidence</h3>
                      {state.evidence.map((ev) => (
                        <a
                          className="evidence-link"
                          key={ev.evidence_id}
                          href={"/api/evidence/" + ev.evidence_id}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Fingerprint size={14} />
                          <div>
                            <strong>{human(ev.kind)}</strong>
                            <small>{ev.sha256_original.slice(0, 22)}…</small>
                          </div>
                          <ArrowRight size={14} />
                        </a>
                      ))}
                    </div>
                  </section>
                </div>
              ) : (
                <section className="panel">
                  <div className="empty-state large">
                    <ShieldCheck size={42} />
                    <h2>No incidents to review.</h2>
                    <p>
                      A quiet porch is a good porch. Run the deposit and removal
                      <br />
                      scenarios to see evidence preservation and human review.
                    </p>
                    <button
                      className="button primary"
                      onClick={() => navigate("replay")}
                    >
                      Open judge replay
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </section>
              )}
            </>
          )}
          {page === "evidence" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Private evidence packet</h2>
                  <p>
                    Original and derived artifacts retain their source,
                    provenance and SHA-256 hashes.
                  </p>
                </div>
                <a className="button" href="/api/export" download>
                  <Download size={16} />
                  Export verified manifest
                </a>
              </div>
              {state.evidence.length === 0 ? (
                <div className="empty-state">
                  <FileCheck2 size={36} />
                  <h3>No evidence collected yet.</h3>
                  <p>
                    Promises close only after their evidence policy is
                    satisfied.
                  </p>
                </div>
              ) : (
                state.evidence.map((item) => (
                  <article className="integration-row" key={item.evidence_id}>
                    <FileCheck2 size={24} />
                    <div>
                      <strong>{human(item.kind)}</strong>
                      <p>
                        {human(item.source_mode)} · {human(item.provenance)} ·{" "}
                        {fmt(item.captured_at)} IST
                      </p>
                      <code style={{ overflowWrap: "anywhere" }}>
                        {item.sha256_original}
                      </code>
                    </div>
                    <a
                      className="button"
                      href={`/api/evidence/${item.evidence_id}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open artifact
                    </a>
                  </article>
                ))
              )}
            </section>
          )}
          {page === "settings" && (
            <div className="settings-layout">
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Connections, with receipts.</h2>
                    <p>Adapter code is not the same as a verified device.</p>
                  </div>
                  <Signal size={18} />
                </div>
                {integrations.map((it) => (
                  <div className="integration-row" key={it.name}>
                    <div className="integration-icon">
                      {it.name === "Fire TV" ? (
                        <Tv />
                      ) : it.name === "Ring" ? (
                        <Video />
                      ) : it.name === "Bee" ? (
                        <AudioLines />
                      ) : (
                        <Radio />
                      )}
                    </div>
                    <div>
                      <strong>{it.name}</strong>
                      <p>{it.reason}</p>
                    </div>
                    <Status status={it.status} />
                  </div>
                ))}
              </section>
              <section className="panel privacy-panel">
                <div className="detail-icon">
                  <ShieldCheck size={26} />
                </div>
                <span className="eyebrow">YOU’RE IN CONTROL</span>
                <h2>
                  Zero reminder prompts.
                  <br />
                  Never zero consent.
                </h2>
                <p>
                  {live
                    ? "Your live household begins with collection disabled."
                    : "All replay data is synthetic."}{" "}
                  Pause collection to stop compilation, camera processing, and
                  new watchdog work.
                </p>
                <button
                  className={`button ${state.consent ? "" : "primary"}`}
                  onClick={() =>
                    void guarded(() =>
                      act("/consent", { enabled: !state.consent }),
                    )
                  }
                >
                  {state.consent ? <Pause size={16} /> : <Play size={16} />}{" "}
                  {state.consent
                    ? "Pause all collection"
                    : live
                      ? "Enable household collection"
                      : "Restore demo consent"}
                </button>
                <div className="privacy-facts">
                  <div>
                    <LockKeyhole size={17} />
                    <span>Household-scoped access</span>
                  </div>
                  <div>
                    <Fingerprint size={17} />
                    <span>SHA-256 artifact integrity</span>
                  </div>
                  <div>
                    <Clock3 size={17} />
                    <span>7-day local evidence retention</span>
                  </div>
                  <div>
                    <Users size={17} />
                    <span>Human approval before consequences</span>
                  </div>
                </div>
                <p className="muted">
                  Live collection is blocked until accounts, permissions, and
                  platform checks are supplied. No secret-entry form is shipped
                  in the browser.
                </p>
              </section>
            </div>
          )}
          <footer className="footer">
            <span>
              <Fingerprint size={13} />
              DONE/IRL
              <span className="footer-divider" />
              APIs lie. Reality doesn’t.
            </span>
            <span>
              Synthetic judge workspace
              <span className="footer-divider" />
              Evidence before closure
            </span>
          </footer>
        </main>
      </div>
      {showNotifications && (
        <div className="notification-drawer">
          <div className="panel-heading">
            <h2>Your private inbox</h2>
            <button
              className="icon-button"
              aria-label="Close notifications"
              onClick={() => setShowNotifications(false)}
            >
              <X size={18} />
            </button>
          </div>
          <p className="drawer-note">
            Companion inbox · native push and earbud whispers are not connected.
          </p>
          {[...state.alerts].reverse().map((a) => (
            <button
              className="notification-card"
              key={a.alert_id}
              onClick={() => {
                const c = state.contracts.find(
                  (c) => c.contract_id === a.contract_id,
                );
                if (c) goContract(c);
                setShowNotifications(false);
              }}
            >
              <span className="eyebrow">
                {human(a.kind)} · {fmt(a.at)}
              </span>
              <p>{a.message}</p>
              <span>
                Open commitment
                <ArrowRight size={13} />
              </span>
            </button>
          ))}
          {!state.alerts.length && (
            <div className="empty-state">
              <Bell size={30} />
              <p>You’re all caught up.</p>
            </div>
          )}
        </div>
      )}
      {showApproval && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Approve simulated report"
          >
            <button
              className="icon-button modal-close"
              aria-label="Close approval"
              onClick={() => setShowApproval(false)}
            >
              <X size={18} />
            </button>
            <FileCheck2 size={32} />
            <span className="eyebrow">EXPLICIT OWNER APPROVAL</span>
            <h2>Review the exact packet.</h2>
            <p>
              This approves a synthetic report to{" "}
              <strong>DEMO_RECEIVER_ONLY</strong>. It contacts no police service
              and generates no official case number.
            </p>
            <code className="hash">{incident?.manifest_hash}</code>
            <p>
              Coverage: {incident?.clip_actual_duration_seconds}-second
              synthetic clip. No live Ring footage.
            </p>
            <label>
              Type APPROVE SIMULATED REPORT
              <input
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoFocus
              />
            </label>
            <button
              className="button primary wide"
              disabled={confirmation !== "APPROVE SIMULATED REPORT" || busy}
              onClick={() =>
                incidentAction("approve-report", {
                  confirmation,
                  destination: "DEMO_RECEIVER_ONLY",
                  manifest_hash: incident.manifest_hash,
                })
              }
            >
              Approve this demo packet
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-symbol">
        <CheckCheck size={22} strokeWidth={2.4} />
      </span>
      <strong>
        DONE<span>/</span>IRL
      </strong>
      <span className="brand-period" />
    </div>
  );
}
function Status({ status }: { status: string }) {
  const cls = [
    "VERIFIED",
    "AUTHORIZED_TRANSFER",
    "SIMULATED_VERIFIED",
  ].includes(status)
    ? "good"
    : ["DISPUTED", "MISSED", "AWAITING_HUMAN_DECISION", "BLOCKED"].includes(
          status,
        )
      ? "attention"
      : "";
  return (
    <span className={"status " + cls}>
      <span />
      {human(status)}
    </span>
  );
}
function Stat({
  icon: Icon,
  label,
  value,
  detail,
  color,
}: {
  icon: typeof Package;
  label: string;
  value: string;
  detail: string;
  color: string;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <div className={"stat-icon " + color}>
          <Icon size={17} />
        </div>
      </div>
      <strong className="stat-value">{value}</strong>
      <div className="stat-detail">{detail}</div>
    </div>
  );
}
function ContractRow({ c, onClick }: { c: Contract; onClick: () => void }) {
  const Icon = icons[c.key] ?? CheckCheck;
  return (
    <button className="contract-row" onClick={onClick}>
      <span className={"contract-icon " + c.key}>
        <Icon size={18} />
      </span>
      <div className="contract-info">
        <strong>{c.title}</strong>
        <small>
          {c.counterparty.label}
          <span>·</span>
          {c.due_at
            ? fmt(c.due_at) + " IST"
            : human(c.deadline_trigger ?? "On evidence")}
        </small>
      </div>
      <Status status={c.status} />
      <ChevronRight size={15} />
    </button>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
