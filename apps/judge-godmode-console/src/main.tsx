import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import {
  Activity,
  ArrowRight,
  AudioLines,
  Bell,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Code2,
  Download,
  Eye,
  FastForward,
  FileCheck2,
  Fingerprint,
  Home,
  Layers3,
  LockKeyhole,
  LockKeyholeOpen,
  LogOut,
  MessageSquareText,
  Package,
  Pause,
  Play,
  Radio,
  RotateCcw,
  ScanLine,
  Settings2,
  ShieldCheck,
  Signal,
  Terminal,
  Tv,
  Users,
  Video,
  X,
} from "lucide-react";
import type {
  Contract,
  State,
} from "../../../packages/physical-contract-schema";
import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "./style.css";
import { PrivacyControls } from "./PrivacyControls";
import { PushOptIn } from "./PushOptIn";
import AlexaSimulator, { resetAlexaMemory } from "./AlexaSimulator";
import { Buddy } from "./Buddy";
import {
  AddPromise,
  IncidentNext,
  StartHere,
  TodaySummary,
  Verdict,
  modalityText,
} from "./guide";
import {
  Brand,
  ContractChip,
  Empty,
  Status,
  api,
  contractSource,
  day,
  due,
  fmt,
  human,
  isOpen,
  sensorVerified,
  plain,
  sleep,
  sourceWords,
  userConfirmed,
  uuid,
} from "./ui";

type Page =
  | "overview"
  | "replay"
  | "contracts"
  | "studio"
  | "alexa"
  | "incidents"
  | "evidence"
  | "settings";
const PAGES: Page[] = [
  "overview",
  "replay",
  "contracts",
  "studio",
  "alexa",
  "incidents",
  "evidence",
  "settings",
];
const labels: Record<Page, string> = {
  overview: "Mission control",
  replay: "Judge replay",
  contracts: "Commitment ledger",
  studio: "Reality-Lock studio",
  alexa: "Alexa+",
  incidents: "Evidence & incidents",
  evidence: "Evidence packet",
  settings: "Connections & privacy",
};
const short: Record<Page, string> = {
  overview: "Control",
  replay: "Replay",
  contracts: "Ledger",
  studio: "Studio",
  alexa: "Alexa+",
  incidents: "Evidence",
  evidence: "Evidence",
  settings: "Privacy",
};
const pageIcons: Record<Page, typeof Home> = {
  overview: Home,
  replay: Layers3,
  contracts: CheckCheck,
  studio: ScanLine,
  alexa: AudioLines,
  incidents: ShieldCheck,
  evidence: FileCheck2,
  settings: Settings2,
};
const subtitles: Partial<Record<Page, string>> = {
  overview:
    "Promises you make out loud, closed only when real-world evidence proves them.",
  replay:
    "Six scenes from one household day, run through the same handlers as live mode.",
  contracts: "Every promise stays open until its evidence policy is met.",
  studio: "Verified squats before evening entertainment.",
  alexa: "Voice-style questions answered only from real MCP tool calls.",
  incidents: "Preserve what happened. You decide what happens next.",
  evidence: "Original and derived artifacts with provenance and SHA-256.",
  settings: "Know what’s connected. Control what’s collected.",
};
// [time, title, source, spec 5.2 button wording]
const stages = [
  [
    "08:15",
    "Morning promises",
    "Bee stream",
    "1. 8:15 AM Morning Promises (Bee Stream)",
  ],
  [
    "14:10",
    "Trust, then verify",
    "Courier deposit",
    "2. 2:10 PM Courier Fake-Out vs. Real Deposit",
  ],
  [
    "15:00",
    "A timely intervention",
    "Deadline auditor",
    "3. 3:00 PM / 3:35 PM T-60m Silent & T-25m Active Escalation",
  ],
  [
    "16:30",
    "Keep a human in the loop",
    "PorchWatchdog",
    "4. 4:30 PM Package Taken → Family vs. Police Report Review",
  ],
  [
    "19:45",
    "The doorway check",
    "Threshold scanner",
    "5. 7:45 PM Returning Home Without Wife's Drinks (Ear Whisper)",
  ],
  [
    "20:30",
    "Earn your evening",
    "Reality-Lock",
    "6. 8:30 PM Fire TV Reality-Lock → Ring Live Camera Squat Unlock",
  ],
];
const stageIcons = [AudioLines, Package, Clock3, ShieldCheck, Home, Activity];
const icons: Record<string, typeof Package> = {
  drinks: Home,
  sister: Users,
  teacher: Clock3,
  squats: Activity,
  parcel: Package,
};
const reducedMotion = () =>
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true;
// Below this width the sidebar is always an icon rail; phones switch to bottom tabs.
const RAIL_QUERY = "(max-width: 959px)";
const SIDEBAR_KEY = "done-irl.sidebar";
const readCollapsed = () => {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "rail";
  } catch {
    return false;
  }
};
const ATTENTION = [
  "AWAITING_HUMAN_DECISION",
  "EVIDENCE_PREPARED",
  "REPORT_APPROVED",
];

const SCRIPTED_FALLBACK: Record<string, string> = {
  real_deposit: "deposit",
  real_no_deposit: "fake",
  real_removal: "unknown",
  real_pickup: "retained",
  real_passerby: "retained",
  real_visible: "visible",
  real_empty: "empty",
  real_bags: "ambiguous",
};

function App() {
  const params = new URLSearchParams(location.search);
  const [state, setState] = useState<State | null>(null),
    [page, setPage] = useState<Page>(
      PAGES.includes(params.get("page") as Page)
        ? (params.get("page") as Page)
        : "overview",
    );
  const [authenticated, setAuthenticated] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [running, setRunning] = useState(false);
  // Real recorded footage by default; scripted marker scenes stay selectable in Judge replay.
  const [branch, setBranch] = useState("real_removal"),
    [deposit, setDeposit] = useState("real_deposit"),
    [arrival, setArrival] = useState("real_empty"),
    [engagement, setEngagement] = useState("disengaged");
  const [selected, setSelected] = useState<Contract | null>(null),
    [showNotifications, setShowNotifications] = useState(false),
    [password, setPassword] = useState(""),
    [username, setUsername] = useState("demo-admin"),
    [loginBusy, setLoginBusy] = useState(false);
  const [consoleTab, setConsoleTab] = useState<"events" | "decisions" | "mcp">(
    "events",
  );
  const [ledgerFilter, setLedgerFilter] = useState("all");
  const [integrations, setIntegrations] = useState<
      { name: string; status: string; reason: string }[]
    >([]),
    [role, setRole] = useState("admin");
  const [playing, setPlaying] = useState(false),
    [showApproval, setShowApproval] = useState(false),
    [confirmation, setConfirmation] = useState("");
  const stop = useRef(false),
    lastEvent = useRef(0);
  const tv = params.has("tv");
  const live = state?.clock_mode === "WALL";
  const [cameraDevices, setCameraDevices] = useState<string[]>([]);
  const [cameraDevice, setCameraDevice] = useState("");
  const [frameTick, setFrameTick] = useState(0);
  const [tvSession, setTvSession] = useState("");
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [narrow, setNarrow] = useState(
    () => window.matchMedia?.(RAIL_QUERY).matches ?? false,
  );
  const [synced, setSynced] = useState(true);
  const [pill, setPill] = useState<{ y: number; h: number } | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const rail = narrow || collapsed;
  useEffect(() => {
    const mq = window.matchMedia?.(RAIL_QUERY);
    if (!mq) return;
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  const toggleSidebar = () =>
    setCollapsed((was) => {
      try {
        localStorage.setItem(SIDEBAR_KEY, was ? "full" : "rail");
      } catch {
        /* storage unavailable: the choice lasts for this visit */
      }
      return !was;
    });
  // One active-item indicator that glides between nav items (and into the footer).
  useLayoutEffect(() => {
    const side = sidebarRef.current;
    if (!side) return;
    const place = () => {
      const el = side.querySelector<HTMLElement>(
        '.nav-item[aria-current="page"]',
      );
      setPill((p) => {
        if (!el) return null;
        const next = { y: el.offsetTop, h: el.offsetHeight };
        return p && p.y === next.y && p.h === next.h ? p : next;
      });
    };
    place();
    const ro = new ResizeObserver(place);
    ro.observe(side);
    return () => ro.disconnect();
  });
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
  const recordedSource = state?.studio?.source === "RECORDED_DEMO_VIDEO";
  useEffect(() => {
    if (!authenticated || live || !recordedSource || page !== "studio") return;
    const timer = setInterval(() => setFrameTick((t) => t + 1), 200);
    return () => clearInterval(timer);
  }, [authenticated, live, recordedSource, page]);
  const studioRunning = state?.studio?.status === "RUNNING";
  useEffect(() => {
    if (!authenticated || page !== "studio" || !studioRunning) return;
    const timer = setInterval(() => void refresh().catch(() => {}), 600);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authenticated, page, studioRunning]);
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
    api("/integrations/status")
      .then((d) => setIntegrations(d.integrations))
      .catch(() => {});
    const es = new EventSource("/api/events/stream");
    es.onopen = () => setSynced(true);
    es.onerror = () => setSynced(false);
    es.addEventListener("ledger", () => {
      setSynced(true);
      lastEvent.current++;
      void refresh().catch(() => {});
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
            "button:not(:disabled),a,input,select,summary",
          ),
        ].filter((el) => el.offsetParent !== null);
        const current = items.indexOf(document.activeElement as HTMLElement);
        const forward = ["ArrowDown", "ArrowRight"].includes(e.key);
        const next =
          (current + (forward ? 1 : -1) + items.length) % items.length;
        e.preventDefault();
        // Ten-foot rule: content without focusable controls (counters, evidence text) must
        // still be reachable. Up/Down scroll the page while the next control is off-screen.
        const page = document.scrollingElement ?? document.documentElement;
        const step = Math.round(window.innerHeight * 0.6);
        const rect = items[next]?.getBoundingClientRect();
        if (e.key === "ArrowDown") {
          const atEnd =
            page.scrollTop + window.innerHeight >= page.scrollHeight - 4;
          if (
            !atEnd &&
            (next <= current || (rect && rect.top > window.innerHeight))
          ) {
            window.scrollBy(0, step);
            return;
          }
        }
        if (e.key === "ArrowUp") {
          if (
            page.scrollTop > 0 &&
            (next >= current || (rect && rect.bottom < 0))
          ) {
            window.scrollBy(0, -step);
            return;
          }
        }
        items[next]?.focus();
      }
      const typing = (e.target as HTMLElement | null)?.matches?.(
        "input, textarea, select",
      );
      if (e.key === "Escape" || (e.key === "Backspace" && !typing)) {
        setSelected(null);
        setPage("overview");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [tv]);
  // An expired or ended session must not hand its Alexa+ transcript to the next account.
  useEffect(() => {
    if (!authenticated) resetAlexaMemory();
  }, [authenticated]);
  // Number keys 1–6 switch views (desktop console only; TV uses the D-pad handler above).
  const shortcut = useRef<(index: number) => void>(() => {});
  useEffect(() => {
    if (tv) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.repeat) return;
      const el = e.target as HTMLElement | null;
      if (el?.closest?.("input, textarea, select, [contenteditable]")) return;
      if (document.querySelector("[aria-modal='true']")) return;
      if (/^[1-9]$/.test(e.key)) shortcut.current(Number(e.key) - 1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [tv]);
  // Escape closes overlays everywhere (not only on TV).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setShowNotifications(false);
      setShowApproval(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
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
    let chosen = branches[index];
    if (chosen.startsWith("real_")) {
      // Real footage is analysed once per server start; until that finishes, use the scripted scene.
      const ready = await fetch("/api/scene/status", {
        credentials: "same-origin",
      })
        .then((r) => (r.ok ? r.json() : { ready: false }))
        .then((j) => Boolean(j.ready))
        .catch(() => false);
      if (!ready) chosen = SCRIPTED_FALLBACK[chosen] ?? chosen;
    }
    await act(`/admin/scenarios/${index}/run`, { branch: chosen });
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
  const navigate = (next: Page, focus: Contract | null = null) => {
    const apply = () => {
      setPage(next);
      setSelected(focus);
    };
    const url = new URL(location.href);
    url.searchParams.set("page", next);
    history.replaceState(null, "", url);
    const doc = document as Document & {
      startViewTransition?: (cb: () => void) => unknown;
    };
    if (next !== page && doc.startViewTransition && !reducedMotion() && !tv)
      doc.startViewTransition(() => flushSync(apply));
    else apply();
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
        navigate("studio");
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
    try {
      await api("/auth/logout", {});
    } catch {
      /* session already gone */
    }
    resetAlexaMemory();
    setAuthenticated(false);
    setState(null);
    setError("");
  };

  if (loading)
    return (
      <div className="loading" role="status">
        <span className="brand-symbol big" aria-hidden>
          <CheckCheck size={26} strokeWidth={2.6} />
        </span>
        <p>Connecting to the reality ledger…</p>
      </div>
    );
  if (!authenticated)
    return (
      <main className="login">
        <div className="login-card">
          <Brand />
          <h1>Life makes promises. Reality keeps score.</h1>
          <p className="login-lede">
            Sign in to your private DONE/IRL workspace.
          </p>
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
            <button className="button primary wide" disabled={loginBusy}>
              {loginBusy ? "Connecting…" : "Open mission control"}
              <ArrowRight size={16} aria-hidden />
            </button>
          </form>
          <p className="login-note">
            <LockKeyhole size={14} aria-hidden />
            <span>
              Passwords are generated locally. Run{" "}
              <code>./scripts/access.sh</code> in your own terminal.
            </span>
          </p>
        </div>
      </main>
    );
  if (!state) return null;
  const admin = role === "admin";
  const pageLabel = (p: Page) =>
    p === "overview" && !admin ? "Today" : labels[p];
  const verified = state.contracts.filter((c) =>
    sensorVerified(c, state.evidence),
  ).length;
  const confirmedByYou = state.contracts.filter((c) =>
    userConfirmed(c, state.evidence),
  ).length;
  const openCount = state.contracts.filter(isOpen).length;
  const incident = state.incidents[0];
  const attention = state.incidents.filter((i) =>
    ATTENTION.includes(i.status),
  ).length;
  // Label incident media by the provenance the server recorded, never by assumption.
  const incidentSource = incident
    ? (state.evidence.find(
        (e) => e.evidence_id === incident.packet.removal_evidence_id,
      )?.provenance ?? "SIMULATED_VERIFIED")
    : "SIMULATED_VERIFIED";
  const footage = incident?.packet.source;
  const incidentSourceText =
    incidentSource === "REAL_RECORDED_STOCK" && footage?.license
      ? `Licensed public footage (${footage.license}, ${footage.author})`
      : sourceWords(incidentSource);
  const latestImage = [...state.evidence]
    .reverse()
    .find((v) => v.mime.startsWith("image/") && v.kind !== "PERSON_CROP");
  const eventList = [...state.events]
    .reverse()
    .filter(
      (ev) =>
        consoleTab !== "decisions" ||
        /verified|evaluated|mismatch|authorized|consent|gap/.test(
          ev.event_type,
        ),
    );
  const latestAlert = state.alerts[state.alerts.length - 1];
  const studio = state.studio;
  const target = studio?.target_reps ?? 15;
  // Pinned recorded workout video decoded server-side through MediaPipe (never the live camera).
  const recordedDemo = !live && studio?.source === "RECORDED_DEMO_VIDEO";
  // Only show the camera surface once a frame has actually been processed (or a live/recorded stream runs).
  const hasFrames =
    live ||
    recordedDemo ||
    (studio?.last_timestamp_ms ?? -1) >= 0 ||
    (studio?.count ?? 0) > 0;
  const playRecordedDemo = () =>
    guarded(async () => {
      cancelReplay();
      if (!state.contracts.length) await runStage(1);
      await act("/studio/recorded/start", { fixture: "squats-15" });
      navigate("studio");
    });
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
  const goContract = (c: Contract) => navigate("contracts", c);
  const navPages: Page[] = admin
    ? ["overview", "replay", "contracts", "studio", "alexa", "incidents"]
    : ["overview", "contracts", "studio", "alexa", "incidents"];
  shortcut.current = (i) => {
    if (navPages[i]) navigate(navPages[i]);
  };
  const addPromise = (className = "") => (
    <AddPromise
      admin={admin}
      now={state.now}
      consent={state.consent}
      busy={busy}
      act={act}
      guarded={guarded}
      className={className}
      newId={uuid}
    />
  );
  const sceneButton = (i: number, variant: "track" | "list") => {
    const [time, title, source, spec] = stages[i];
    const Icon = stageIcons[i];
    const done = state.scenario > i;
    const current = state.scenario === i + 1;
    return (
      <li key={time}>
        <button
          className={`scene in-${variant} ${current ? "current" : ""} ${done ? "done" : ""}`}
          disabled={busy || running || !admin}
          onClick={() => void guarded(() => runStage(i + 1))}
          aria-label={`${i + 1}. ${time} ${title} — ${spec}`}
          aria-current={current ? "step" : undefined}
          title={spec}
        >
          <span className="scene-node" aria-hidden>
            {done && !current ? <Check size={15} /> : <Icon size={15} />}
          </span>
          <span className="scene-text">
            <span className="scene-time">
              {variant === "track" && time}
              <span className="scene-source">{source}</span>
            </span>
            <strong>{variant === "list" ? spec : title}</strong>
          </span>
        </button>
      </li>
    );
  };
  const contractCard = (c: Contract) => {
    const Icon = icons[c.key] ?? CheckCheck;
    return (
      <button
        className="contract-card"
        key={c.contract_id}
        onClick={() => goContract(c)}
      >
        <span className={`contract-icon ${c.key}`} aria-hidden>
          <Icon size={16} />
        </span>
        <span className="contract-text">
          <strong>{c.title}</strong>
          <small>
            {c.counterparty.label} ·{" "}
            {c.due_at
              ? due(c.due_at, state.now)
              : human(c.deadline_trigger ?? "On evidence")}
          </small>
        </span>
        <span className="contract-meta">
          <ContractChip c={c} evidence={state.evidence} />
        </span>
      </button>
    );
  };

  const consentBanner = !state.consent && (
    <div className="banner warning" role="status">
      <Pause size={15} aria-hidden />
      <span>
        Collection paused. Watchdogs and camera processing require consent.
      </span>
      <button
        className="button small"
        disabled={busy}
        onClick={() => void guarded(() => act("/consent", { enabled: true }))}
      >
        {live ? "Enable household collection" : "Restore demo consent"}
      </button>
    </div>
  );

  return (
    <div
      className={`app ${tv ? "tv-mode" : ""} ${rail ? "rail" : ""}`}
      data-page={page}
    >
      <aside className="sidebar" aria-label="Primary" ref={sidebarRef}>
        <div className="side-head">
          <Brand />
        </div>
        {!narrow && (
          <button
            className="side-toggle has-tip"
            onClick={toggleSidebar}
            aria-label={rail ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!rail}
          >
            <ChevronLeft size={14} strokeWidth={2.4} aria-hidden />
            <span className="tip" aria-hidden>
              {rail ? "Expand sidebar" : "Collapse sidebar"}
            </span>
          </button>
        )}
        <div className="household">
          <span className="household-avatar" aria-hidden>
            {live ? "H" : "D"}
          </span>
          <span className="side-label">
            {live ? "My household" : "Demo day"}
          </span>
        </div>
        {pill && (
          <span
            className="side-indicator"
            aria-hidden
            style={{ transform: `translateY(${pill.y}px)`, height: pill.h }}
          />
        )}
        <nav className="nav">
          {navPages.map((id, i) => {
            const Icon = pageIcons[id];
            const active =
              page === id || (id === "incidents" && page === "evidence");
            const count = id === "incidents" ? attention : 0;
            return (
              <button
                key={id}
                className={`nav-item ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
                aria-label={pageLabel(id)}
                aria-keyshortcuts={String(i + 1)}
                onClick={() => navigate(id)}
              >
                <span className="nav-icon" aria-hidden>
                  <Icon size={18} />
                  {count > 0 && <span className="nav-dot" />}
                </span>
                <span className="side-label" aria-hidden>
                  {pageLabel(id)}
                </span>
                {count > 0 && (
                  <span className="nav-count" aria-hidden>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <div className="side-foot">
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            aria-current={page === "settings" ? "page" : undefined}
            aria-label="Connections & privacy"
            onClick={() => navigate("settings")}
          >
            <span className="nav-icon" aria-hidden>
              <Settings2 size={18} />
            </span>
            <span className="side-label" aria-hidden>
              Connections & privacy
            </span>
          </button>
          <div
            className={`side-status has-tip ${synced ? "" : "offline"}`}
            role="status"
            tabIndex={0}
            aria-describedby="sync-tip"
          >
            <span className="status-dot" aria-hidden />
            <span className="status-text">
              {synced ? "Synced" : "Reconnecting…"}
            </span>
            <span className="tip" id="sync-tip" role="tooltip">
              {synced
                ? "Ledger synced · changes saved as they happen"
                : "Connection lost · retrying in the background"}
            </span>
          </div>
          <button
            className="nav-item"
            aria-label="Sign out"
            onClick={() => void logOut()}
          >
            <span className="nav-icon" aria-hidden>
              <LogOut size={18} />
            </span>
            <span className="side-label" aria-hidden>
              Sign out
            </span>
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-title">
            <span className="mobile-brand">
              <Brand compact />
            </span>
            <span className="crumb">{pageLabel(page)}</span>
          </div>
          <div className="topbar-right">
            {(busy || running) && (
              <span className="working" role="status">
                <span className="spinner" aria-hidden />
                {running ? "Replaying" : "Working"}
              </span>
            )}
            {!live && (
              <span
                className="demo-chip has-tip"
                tabIndex={0}
                aria-describedby="demo-tip"
              >
                Demo day
                <span className="tip" id="demo-tip" role="tooltip">
                  Replay of a scripted day. Your own household runs live.
                </span>
              </span>
            )}
            <span className="clock" title={day(state.now)}>
              <Clock3 size={14} aria-hidden />
              {fmt(state.now)} IST
            </span>
            {tvSession && (
              <span
                className="household-tag"
                title="Authenticated session; device runtime proof is separate"
              >
                TV session {tvSession.slice(-8)}
              </span>
            )}
            <button
              className="icon-button hide-mobile"
              aria-label="Open TV preview"
              title="Open TV preview (web, not device proof)"
              onClick={() => window.open("/?tv=1", "_blank", "noopener")}
            >
              <Tv size={17} aria-hidden />
            </button>
            <a
              className="icon-button hide-mobile"
              href="/api/export"
              download
              aria-label="Export evidence"
              title="Export evidence"
            >
              <Download size={17} aria-hidden />
            </a>
            <button
              className="icon-button notification-button"
              aria-label="Open notifications"
              aria-expanded={showNotifications}
              onClick={() => setShowNotifications(!showNotifications)}
            >
              <Bell size={17} aria-hidden />
              {state.alerts.length > 0 && <i aria-hidden />}
            </button>
            <button
              className="icon-button show-mobile"
              aria-label="Connections & privacy"
              onClick={() => navigate("settings")}
            >
              <Settings2 size={17} aria-hidden />
            </button>
            <button
              className="icon-button show-mobile"
              aria-label="Sign out"
              onClick={() => void logOut()}
            >
              <LogOut size={17} aria-hidden />
            </button>
          </div>
        </header>
        <main className="content" id="main">
          {tv && (
            <div className="tv-navigation">
              {(["overview", "contracts", "incidents", "studio"] as Page[]).map(
                (id) => (
                  <button
                    key={id}
                    className={`button ${page === id ? "active" : ""}`}
                    onClick={() => navigate(id)}
                  >
                    {pageLabel(id)}
                  </button>
                ),
              )}
            </div>
          )}
          <div className="view" key={page}>
            <header className="page-head">
              <div className="page-title">
                <h1>
                  {pageLabel(page)}
                  <span className="heading-dot">.</span>
                </h1>
                <p>
                  {page === "overview" && !admin
                    ? `${day(state.now)} · ${openCount} open · ${verified} verified · ${confirmedByYou} confirmed by you`
                    : subtitles[page]}
                </p>
              </div>
              {page === "overview" && admin && (
                <div className="page-actions">
                  {(running || playing) && (
                    <button className="button" onClick={cancelReplay}>
                      <Pause size={15} aria-hidden />
                      Pause
                    </button>
                  )}
                  <button
                    className="button ghost"
                    disabled={busy}
                    onClick={reset}
                  >
                    <RotateCcw size={15} aria-hidden />
                    Reset day
                  </button>
                  <button
                    className="button primary"
                    disabled={running || busy}
                    onClick={() => void fullDay()}
                  >
                    <Play size={15} fill="currentColor" aria-hidden />
                    {running ? "Replaying the day…" : "Run the full day"}
                  </button>
                </div>
              )}
            </header>
            {error && (
              <div className="banner error" role="alert">
                <span>{error}</span>
                <button
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => setError("")}
                >
                  <X size={16} aria-hidden />
                </button>
              </div>
            )}
            {consentBanner}

            {page === "overview" && !admin && (
              <Buddy
                state={state}
                act={act}
                busy={busy}
                guarded={guarded}
                onOpen={goContract}
              />
            )}

            {page === "overview" && admin && (
              <div className="overview">
                <section className="panel day-panel" aria-label="The day">
                  <div className="panel-head">
                    <h2>The canonical day</h2>
                    <span className="muted-text">
                      {state.scenario
                        ? `Scene ${state.scenario} of 6 · ${stages[state.scenario - 1][1]}`
                        : "Six scenes, one connected story"}
                    </span>
                  </div>
                  <ol
                    className="track"
                    style={
                      {
                        "--p": Math.max(0, state.scenario - 1) / 5,
                      } as React.CSSProperties
                    }
                  >
                    {stages.map((_, i) => sceneButton(i, "track"))}
                  </ol>
                </section>
                <section className="panel promises-panel" aria-label="Promises">
                  <div className="panel-head">
                    <h2>Promises</h2>
                    <span className="muted-text">
                      {verified} verified
                      {confirmedByYou
                        ? ` · ${confirmedByYou} confirmed by you`
                        : ""}{" "}
                      · {openCount} open
                    </span>
                    <button
                      className="text-button"
                      onClick={() => navigate("contracts")}
                    >
                      Open ledger <ArrowRight size={14} aria-hidden />
                    </button>
                  </div>
                  {state.contracts.length ? (
                    <>
                      <div
                        className={`card-grid ${state.scenario >= 2 ? "with-today" : ""}`}
                      >
                        {state.contracts.map(contractCard)}
                      </div>
                      {state.scenario >= 2 && (
                        <TodaySummary
                          contracts={state.contracts}
                          evidence={state.evidence}
                          incidentPending={
                            incident?.status === "AWAITING_HUMAN_DECISION"
                          }
                          onOpen={goContract}
                          onGo={(p) => navigate(p)}
                        />
                      )}
                      {addPromise("compact")}
                    </>
                  ) : (
                    <StartHere
                      disabled={busy || running}
                      onPlay={() => void fullDay()}
                      onOpen={(p) => navigate(p)}
                    >
                      <div className="start-add">
                        <span>Or say a promise of your own:</span>
                        {addPromise()}
                      </div>
                    </StartHere>
                  )}
                </section>
                <div className="overview-side">
                  <section className="panel now-panel" aria-label="Right now">
                    <div className="panel-head">
                      <h2>Right now</h2>
                      <span className="live-dot" aria-hidden />
                    </div>
                    {latestAlert ? (
                      <div className="now-alert" data-kind={latestAlert.kind}>
                        <span className="kind">
                          {human(latestAlert.kind)} · {fmt(latestAlert.at)}
                        </span>
                        <p>{plain(latestAlert.message)}</p>
                      </div>
                    ) : (
                      <p className="muted-text">
                        Quiet so far. Alerts appear here as the day unfolds.
                      </p>
                    )}
                    <dl className="now-stats">
                      <div>
                        <dt>Verified</dt>
                        <dd>{verified}</dd>
                      </div>
                      <div>
                        <dt>Watchdogs</dt>
                        <dd>
                          {
                            state.subagents.filter(
                              (a) => a.status === "WATCHING",
                            ).length
                          }
                        </dd>
                      </div>
                      <div>
                        <dt>Evidence</dt>
                        <dd>{state.evidence.length}</dd>
                      </div>
                      <div>
                        <dt>Events</dt>
                        <dd>{state.events.length}</dd>
                      </div>
                    </dl>
                  </section>
                  <nav className="panel jump" aria-label="Explore">
                    {(
                      [
                        [
                          "studio",
                          "Studio",
                          "Reality-Lock · pose-verified workout",
                        ],
                        [
                          "alexa",
                          "Alexa+",
                          "Voice answers from MCP tool calls",
                        ],
                        [
                          "incidents",
                          "Evidence",
                          "Incident review · SHA-256 packet",
                        ],
                        [
                          "settings",
                          "Privacy",
                          "Connections, consent, retention",
                        ],
                      ] as [Page, string, string][]
                    ).map(([id, name, detail]) => {
                      const Icon = pageIcons[id];
                      return (
                        <button
                          key={id}
                          className="jump-tile"
                          onClick={() => navigate(id)}
                        >
                          <Icon size={17} aria-hidden />
                          <span>
                            <strong>{name}</strong>
                            <small>{detail}</small>
                          </span>
                          <ChevronRight size={15} aria-hidden />
                        </button>
                      );
                    })}
                  </nav>
                </div>
              </div>
            )}

            {page === "replay" && (
              <div className="console">
                <div
                  className="console-bar"
                  role="toolbar"
                  aria-label="Replay controls"
                >
                  <button
                    className="button small"
                    disabled={busy}
                    onClick={reset}
                  >
                    <RotateCcw size={14} aria-hidden /> Reset
                  </button>
                  <button
                    className="button small primary"
                    disabled={running || busy || !admin}
                    onClick={() => void fullDay()}
                  >
                    <Play size={13} fill="currentColor" aria-hidden />
                    {running ? "Replaying…" : "Run full day"}
                  </button>
                  <button
                    className="button small"
                    disabled={!(running || playing)}
                    onClick={cancelReplay}
                  >
                    <Pause size={14} aria-hidden /> Pause
                  </button>
                  <span className="bar-divider" aria-hidden />
                  <button
                    className="button small"
                    disabled={busy}
                    onClick={() =>
                      void guarded(() =>
                        act("/admin/clock/advance", { minutes: 25 }),
                      )
                    }
                  >
                    <FastForward size={14} aria-hidden /> Advance 25 minutes
                  </button>
                  <span className="bar-clock">
                    <Clock3 size={14} aria-hidden /> {fmt(state.now)} IST
                  </span>
                  <span className="bar-divider" aria-hidden />
                  <select
                    aria-label="Failure injection"
                    defaultValue=""
                    className="small"
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
                  <a className="button small" href="/api/export" download>
                    <Download size={14} aria-hidden /> Export
                  </a>
                </div>
                <aside className="panel console-scenes" aria-label="Scenes">
                  <div className="panel-head">
                    <h2>Scenes</h2>
                    <span className="muted-text">{state.scenario}/6</span>
                  </div>
                  <ol className="scene-list">
                    {stages.map((_, i) => sceneButton(i, "list"))}
                  </ol>
                  <fieldset className="forks">
                    <legend title="Reset before replaying a scene with a new branch">
                      Scenario forks
                    </legend>
                    <label>
                      Courier
                      <select
                        aria-label="Courier"
                        value={deposit}
                        onChange={(e) => setDeposit(e.target.value)}
                      >
                        <option value="deposit">Real deposit</option>
                        <option value="fake">Courier fake-out</option>
                        <optgroup label="Licensed public footage">
                          <option value="real_deposit">Real deposit</option>
                          <option value="real_no_deposit">
                            Real no deposit
                          </option>
                        </optgroup>
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
                        <option value="family">Family pickup</option>
                        <option value="retained">Parcel remains</option>
                        <optgroup label="Licensed public footage">
                          <option value="real_removal">Real removal</option>
                          <option value="real_pickup">Real owner pickup</option>
                          <option value="real_passerby">Real passer-by</option>
                        </optgroup>
                      </select>
                    </label>
                    <label>
                      Meeting context
                      <select
                        aria-label="Meeting context"
                        value={engagement}
                        onChange={(e) => setEngagement(e.target.value)}
                      >
                        <option value="disengaged">Unconfirmed</option>
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
                        <option value="ambiguous">Occluded</option>
                        <optgroup label="Licensed public footage">
                          <option value="real_visible">
                            Real: bag visible
                          </option>
                          <option value="real_empty">Real: hands empty</option>
                        </optgroup>
                      </select>
                    </label>
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() =>
                        void guarded(() => act("/admin/sister-proof"))
                      }
                    >
                      Inject sister call proof
                    </button>
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() =>
                        void guarded(() => act("/admin/owner-pickup"))
                      }
                    >
                      Observe owner pickup
                    </button>
                  </fieldset>
                </aside>
                <section
                  className="panel console-center"
                  aria-label="Contracts and pipeline"
                >
                  <ol className="pipeline" aria-label="Pipeline">
                    {(
                      [
                        [
                          "Stream input",
                          state.events.filter((e) =>
                            e.event_type.startsWith("bee."),
                          ).length,
                        ],
                        ["Orchestrator", state.events.length],
                        ["Contracts", state.contracts.length],
                        ["Sub-agents", state.subagents.length],
                        ["Evidence", state.evidence.length],
                        ["Screen", state.alerts.length],
                      ] as [string, number][]
                    ).map(([name, n]) => (
                      <li key={name} className={n ? "on" : ""} title={name}>
                        <strong key={n}>{n}</strong>
                        <span>{name}</span>
                      </li>
                    ))}
                  </ol>
                  <div className="psc-list">
                    {state.contracts.length ? (
                      state.contracts.map((c) => (
                        <button
                          className="psc"
                          key={c.contract_id}
                          onClick={() => goContract(c)}
                        >
                          <strong>{c.title}</strong>
                          <span className="psc-meta">
                            <ContractChip c={c} evidence={state.evidence} />
                          </span>
                        </button>
                      ))
                    ) : (
                      <Empty
                        icon={AudioLines}
                        title="Start with scene 1 to compile promises."
                      />
                    )}
                  </div>
                  <div className="console-split">
                    <figure className="frame">
                      {latestImage ? (
                        <img
                          src={"/api/evidence/" + latestImage.evidence_id}
                          alt="Latest processed porch frame"
                        />
                      ) : (
                        <div className="frame-empty">
                          <Video size={22} aria-hidden />
                          <span>Camera scenes show their processed frame</span>
                        </div>
                      )}
                      <figcaption>
                        <span>
                          {latestImage
                            ? `Latest frame · ${fmt(latestImage.captured_at)} IST`
                            : "Porch camera"}
                        </span>
                      </figcaption>
                    </figure>
                    <div className="events">
                      <div className="tabs" role="tablist">
                        {(["events", "decisions", "mcp"] as const).map(
                          (tab) => (
                            <button
                              role="tab"
                              aria-selected={consoleTab === tab}
                              className={consoleTab === tab ? "active" : ""}
                              onClick={() => setConsoleTab(tab)}
                              key={tab}
                            >
                              {tab === "mcp"
                                ? "MCP"
                                : tab === "events"
                                  ? "Events"
                                  : "Decisions"}
                            </button>
                          ),
                        )}
                        <span>{state.events.length}</span>
                      </div>
                      {consoleTab === "mcp" ? (
                        <div className="mcp-inspector">
                          <Code2 size={18} aria-hidden />
                          <p>
                            Streamable HTTP MCP at <code>/mcp/</code> shares
                            this ledger. Scene buttons use REST ingestion, not
                            fabricated MCP calls; live MCP traffic appears in
                            the Alexa+ panel.
                          </p>
                        </div>
                      ) : (
                        <div className="event-scroll">
                          {eventList.length ? (
                            eventList.map((ev) => (
                              <details key={ev.event_id}>
                                <summary>
                                  <time>{fmt(ev.occurred_at)}</time>
                                  <strong>{ev.event_type}</strong>
                                </summary>
                                <pre>{JSON.stringify(ev, null, 2)}</pre>
                              </details>
                            ))
                          ) : (
                            <Empty
                              icon={Terminal}
                              title="No matching events yet."
                            />
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </section>
                <div className="console-alexa">
                  <AlexaSimulator state={state} compact />
                </div>
              </div>
            )}

            {page === "alexa" && (
              <div className="alexa-page">
                <AlexaSimulator state={state} />
              </div>
            )}

            {page === "contracts" && (
              <div className="ledger">
                <section className="panel ledger-list" aria-label="Commitments">
                  <div className="panel-head">
                    <h2>
                      All commitments{" "}
                      <span className="count">{state.contracts.length}</span>
                    </h2>
                  </div>
                  <div className="segmented" role="group" aria-label="Filter">
                    {(
                      [
                        ["all", "All"],
                        ["check", "Needs your check"],
                        ["open", "Not yet verified"],
                        ["verified", "Verified"],
                        ["missed", "Missed"],
                      ] as const
                    ).map(([id, name]) => (
                      <button
                        key={id}
                        aria-pressed={ledgerFilter === id}
                        onClick={() => setLedgerFilter(id)}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                  <div className="ledger-rows">
                    {state.contracts
                      .filter((c) =>
                        ledgerFilter === "all"
                          ? true
                          : ledgerFilter === "check"
                            ? [
                                "NEEDS_CONFIRMATION",
                                "EVIDENCE_PENDING",
                                "DISPUTED",
                              ].includes(c.status)
                            : ledgerFilter === "verified"
                              ? c.status === "VERIFIED"
                              : ledgerFilter === "missed"
                                ? c.status === "MISSED"
                                : ["ACTIVE", "ENGAGED", "DISCOVERED"].includes(
                                    c.status,
                                  ),
                      )
                      .map((c) => {
                        const Icon = icons[c.key] ?? CheckCheck;
                        return (
                          <button
                            className={`ledger-row ${selected?.contract_id === c.contract_id ? "selected" : ""}`}
                            key={c.contract_id}
                            onClick={() => setSelected(c)}
                          >
                            <span
                              className={`contract-icon ${c.key}`}
                              aria-hidden
                            >
                              <Icon size={16} />
                            </span>
                            <span className="contract-text">
                              <strong>{c.title}</strong>
                              <small>
                                {c.counterparty.label} ·{" "}
                                {c.due_at
                                  ? due(c.due_at, state.now) + " IST"
                                  : human(c.deadline_trigger ?? "On evidence")}
                              </small>
                            </span>
                            <span className="row-meta">
                              <ContractChip c={c} evidence={state.evidence} />
                            </span>
                          </button>
                        );
                      })}
                    {!state.contracts.length && (
                      <Empty icon={CheckCheck} title="Your ledger is clear.">
                        {admin && (
                          <button
                            className="button small"
                            disabled={busy}
                            onClick={() => void guarded(() => runStage(1))}
                          >
                            Start the morning <Play size={13} aria-hidden />
                          </button>
                        )}
                      </Empty>
                    )}
                  </div>
                  {addPromise("compact")}
                </section>
                <section
                  className="panel ledger-detail"
                  aria-label="Commitment detail"
                >
                  {selected ? (
                    (() => {
                      const c =
                        state.contracts.find(
                          (c) => c.contract_id === selected.contract_id,
                        ) ?? selected;
                      const Icon = icons[c.key] ?? CheckCheck;
                      const linked = state.evidence.filter((ev) =>
                        c.evidence_ids.includes(ev.evidence_id),
                      );
                      return (
                        <div className="detail" key={c.contract_id}>
                          <div className="detail-top">
                            <span
                              className={`contract-icon big ${c.key}`}
                              aria-hidden
                            >
                              <Icon size={22} />
                            </span>
                            <div>
                              <span className="eyebrow">
                                Physical state contract · rev {c.revision}
                              </span>
                              <h2>{c.title}</h2>
                            </div>
                          </div>
                          <div className="detail-chips">
                            <ContractChip c={c} evidence={state.evidence} />
                          </div>
                          <Verdict
                            c={c}
                            evidence={state.evidence}
                            onStudio={() => navigate("studio")}
                          />
                          <blockquote>“{c.original_utterance}”</blockquote>
                          <dl className="facts">
                            <dt>Counterparty</dt>
                            <dd>{c.counterparty.label}</dd>
                            <dt>Due / trigger</dt>
                            <dd>
                              {c.due_at
                                ? due(c.due_at, state.now) + " IST"
                                : human(c.deadline_trigger ?? "On evidence")}
                            </dd>
                            <dt>Verification</dt>
                            <dd>{modalityText(c.verification_modality)}</dd>
                            <dt>Source</dt>
                            <dd>{sourceWords(contractSource(c))}</dd>
                            <dt>Evidence</dt>
                            <dd>
                              {linked.length
                                ? linked
                                    .map(
                                      (ev) =>
                                        `${human(ev.kind)} (${sourceWords(ev.provenance).toLowerCase()})`,
                                    )
                                    .join(", ")
                                : "None yet"}
                            </dd>
                          </dl>
                          {c.proposed_amendment && (
                            <div className="note amend">
                              Another speaker proposed a new deadline:{" "}
                              {fmt(c.proposed_amendment.due_at)} IST. Not
                              applied; the original deadline stands.
                            </div>
                          )}
                          {c.custody_status && (
                            <div className="note">
                              Custody: {human(c.custody_status)}
                            </div>
                          )}
                          {c.visibility && (
                            <div className="note">
                              Visibility: {human(c.visibility)}. A supporting
                              observation is not final closure.
                            </div>
                          )}
                          {c.scheduled_jobs.length > 0 && (
                            <div className="schedule">
                              {c.scheduled_jobs.map((j) => (
                                <div className="schedule-row" key={j.kind}>
                                  <Clock3 size={13} aria-hidden />
                                  <strong>{j.kind}</strong>
                                  <time>{fmt(j.at)}</time>
                                  <small>{human(j.status)}</small>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="detail-actions">
                            {c.status === "NEEDS_CONFIRMATION" && (
                              <>
                                <button
                                  className="button primary"
                                  disabled={busy}
                                  onClick={() =>
                                    void guarded(() =>
                                      act(
                                        `/contracts/${c.contract_id}/confirm`,
                                        {
                                          action: "accept",
                                          revision: c.revision,
                                        },
                                      ),
                                    )
                                  }
                                >
                                  Accept promise
                                </button>
                                <button
                                  className="button"
                                  disabled={busy}
                                  onClick={() =>
                                    void guarded(() =>
                                      act(
                                        `/contracts/${c.contract_id}/confirm`,
                                        {
                                          action: "reject",
                                          revision: c.revision,
                                        },
                                      ),
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
                                disabled={busy}
                                onClick={() =>
                                  void guarded(() =>
                                    act(`/contracts/${c.contract_id}/confirm`, {
                                      action: "confirm-drinks",
                                      revision: c.revision,
                                    }),
                                  )
                                }
                              >
                                Confirm I have the drinks{" "}
                                <Check size={14} aria-hidden />
                              </button>
                            )}
                            {c.key.startsWith("gen_") &&
                              [
                                "ACTIVE",
                                "ENGAGED",
                                "EVIDENCE_PENDING",
                                "MISSED",
                              ].includes(c.status) &&
                              c.verification_modality !==
                                "FIRE_TV_LIVE_POSE_CAMERA" && (
                                <button
                                  className="button"
                                  disabled={busy}
                                  title="Recorded as your confirmation, not sensor proof"
                                  onClick={() =>
                                    void guarded(() =>
                                      act(
                                        `/contracts/${c.contract_id}/confirm`,
                                        {
                                          action: "confirm-done",
                                          revision: c.revision,
                                        },
                                      ),
                                    )
                                  }
                                >
                                  Confirm done <CheckCheck size={14} />
                                </button>
                              )}
                            {isOpen(c) && (
                              <button
                                className="text-button"
                                disabled={busy}
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
                        </div>
                      );
                    })()
                  ) : (
                    <Empty icon={Fingerprint} title="Select a commitment.">
                      <p>See its origin, evidence policy and schedule.</p>
                    </Empty>
                  )}
                </section>
              </div>
            )}

            {page === "studio" && (
              <div className="studio">
                <section
                  className={`studio-screen ${studio?.gate === "UNLOCKED" ? "unlocked" : ""}`}
                  aria-label="Camera"
                >
                  <div className="studio-overlay top">
                    <span className="studio-state">
                      <span className="pulse-dot" aria-hidden />
                      {studio?.status === "RUNNING" && !hasFrames
                        ? "READY"
                        : studio?.status === "RUNNING"
                          ? live
                            ? "PROCESSING RING FRAMES"
                            : "PROCESSING FRAMES"
                          : studio
                            ? human(studio.status).toUpperCase()
                            : "CAMERA STUDIO"}
                    </span>
                    {live && (
                      <span className="studio-source">
                        {studio?.source_mode === "LIVE_VERIFIED" &&
                        studio?.status === "RUNNING"
                          ? "LIVE RING"
                          : "AWAITING LIVE CAMERA"}
                      </span>
                    )}
                  </div>
                  {studio && hasFrames && (
                    <span className="frame-wait" role="status">
                      Waiting for the first processed frame…
                    </span>
                  )}
                  {studio && !hasFrames ? (
                    <div className="studio-intro">
                      <ScanLine size={44} aria-hidden />
                      <h2>Ready when you are.</h2>
                      <p>
                        {target} full squats unlock your evening. Start the
                        workout and every rep is counted from the video.
                      </p>
                    </div>
                  ) : studio ? (
                    <img
                      className="pose-feed"
                      onLoad={(e) => (e.currentTarget.style.opacity = "1")}
                      onError={(e) => (e.currentTarget.style.opacity = "0")}
                      src={
                        live
                          ? `/api/camera/frame?v=${frameTick}`
                          : recordedDemo
                            ? `/api/studio/recorded/frame?v=${frameTick}`
                            : `/api/studio/frame?v=${studio.fixture_frame_index ?? 0}-${studio.angle}`
                      }
                      alt={
                        live
                          ? "Authorized Ring frames with MediaPipe skeleton"
                          : recordedDemo
                            ? "Recorded workout with MediaPipe skeleton overlay"
                            : "Marker pose tracking with skeleton overlay"
                      }
                    />
                  ) : (
                    <div className="studio-intro">
                      <ScanLine size={44} aria-hidden />
                      <h2>Your living room. Your proof.</h2>
                      <p>
                        {live
                          ? "Choose a linked Ring camera. MediaPipe evaluates complete movements."
                          : "Recommended: play the recorded workout. Every full squat is counted from the video by pose landmarks."}
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
                      {live ? (
                        <button
                          className="button"
                          onClick={openStudio}
                          disabled={busy || !cameraDevice}
                        >
                          <Video size={15} aria-hidden />
                          Connect Ring camera
                        </button>
                      ) : (
                        <button
                          className="button primary"
                          disabled={playing || busy}
                          onClick={() => void playRecordedDemo()}
                        >
                          <Video size={15} aria-hidden />
                          Play recorded workout
                        </button>
                      )}
                    </div>
                  )}
                  {studio?.gate === "UNLOCKED" && (
                    <div className="unlock-burst" aria-hidden>
                      <LockKeyholeOpen size={34} />
                    </div>
                  )}
                  <div className="studio-overlay bottom">
                    <span className="gate">
                      {studio?.gate === "UNLOCKED" ? (
                        <LockKeyholeOpen size={14} aria-hidden />
                      ) : (
                        <LockKeyhole size={14} aria-hidden />
                      )}
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
                <aside className="panel workout" aria-label="Workout">
                  <span className="eyebrow">A promise to yourself</span>
                  <h2>{target} full squats</h2>
                  <div
                    className={`rep-ring ${studio?.gate === "UNLOCKED" ? "unlocked" : ""}`}
                    style={
                      {
                        "--progress": `${Math.min(1, (studio?.count ?? 0) / target) * 100}%`,
                      } as React.CSSProperties
                    }
                    role="img"
                    aria-label={`${studio?.count ?? 0} of ${target} verified squats`}
                  >
                    <div>
                      <strong key={studio?.count ?? 0}>
                        {(studio?.count ?? 0).toString().padStart(2, "0")}
                      </strong>
                      <span>/ {target} VERIFIED CYCLES</span>
                    </div>
                  </div>
                  <dl className="workout-metrics">
                    <div>
                      <dt>Knee angle</dt>
                      <dd>
                        {studio?.angle ?? "—"}
                        {studio ? "°" : ""}
                      </dd>
                    </div>
                    <div>
                      <dt>Phase</dt>
                      <dd>{human(studio?.phase ?? "Not started")}</dd>
                    </div>
                  </dl>
                  {studio?.gate === "UNLOCKED" ? (
                    <div className="success" role="status">
                      <ShieldCheck size={20} aria-hidden />
                      <div>
                        <strong>Promise kept. Evidence saved.</strong>
                        <p>
                          {live
                            ? `${target} camera-backed cycles verified.`
                            : `${target} full cycles verified.`}{" "}
                          In-app gate unlocked.
                        </p>
                      </div>
                    </div>
                  ) : live ? (
                    <div className="workout-buttons">
                      <button
                        className="button primary wide"
                        onClick={openStudio}
                        disabled={busy || !cameraDevice}
                      >
                        Connect camera
                      </button>
                      <button
                        className="button wide"
                        disabled={busy}
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
                    <div className="workout-buttons">
                      {studio && (
                        <button
                          className="button primary wide"
                          disabled={
                            playing ||
                            busy ||
                            studio?.status === "COMPLETED" ||
                            studio?.status === "RUNNING"
                          }
                          onClick={() => void playRecordedDemo()}
                        >
                          <Video size={15} aria-hidden />
                          Play recorded workout
                        </button>
                      )}
                      <button
                        className="button wide"
                        disabled={playing || busy || !admin}
                        onClick={() => void workout()}
                      >
                        <Play size={14} aria-hidden />
                        {playing ? "Processing marker frames…" : "Run workout"}
                      </button>
                    </div>
                  )}
                  {playing && (
                    <button className="button wide" onClick={cancelReplay}>
                      <Pause size={15} aria-hidden />
                      Pause replay
                    </button>
                  )}
                  {studio && studio.status !== "COMPLETED" && (
                    <div className="workout-secondary">
                      <button
                        className="text-button"
                        disabled={busy}
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
                        disabled={busy}
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
                  <details className="disclosure">
                    <summary>How verification works</summary>
                    <p>
                      Frames are decoded into pose landmarks and checked for
                      full cycles with timestamps and quality gates. Only
                      complete movements count toward the target.
                    </p>
                    <p>
                      Voluntary movement recognition, not medical guidance.
                      Override opens the in-app gate and keeps the physical
                      promise unverified. No other apps are locked.
                    </p>
                  </details>
                </aside>
              </div>
            )}

            {page === "incidents" &&
              (incident ? (
                <div className="incident">
                  <section
                    className="panel incident-main"
                    aria-label="Incident review"
                  >
                    <div className="panel-head">
                      <div>
                        <span className="eyebrow">Human review required</span>
                        <h2>A package moved. Was it authorized?</h2>
                      </div>
                      <Status status={incident.status} />
                    </div>
                    <div className="incident-media">
                      <figure>
                        <img
                          src={
                            "/api/evidence/" +
                            (incident.packet.annotated_frame_evidence_id ??
                              incident.packet.source_frame_evidence_id ??
                              incident.packet.removal_evidence_id)
                          }
                          alt="Annotated removal frame"
                        />
                        <figcaption>
                          Removal · {fmt(incident.detected_at)} IST
                        </figcaption>
                      </figure>
                      {incident.packet.source_clip_evidence_id && (
                        <figure>
                          <video
                            controls
                            preload="metadata"
                            aria-label="15-second removal clip"
                            src={
                              "/api/evidence/" +
                              incident.packet.source_clip_evidence_id
                            }
                          />
                          <figcaption>
                            {incident.clip_actual_duration_seconds}s clip
                          </figcaption>
                        </figure>
                      )}
                    </div>
                    <p className="incident-copy">
                      The tracked parcel moved from the porch toward the street.
                      Observation, not accusation: identity and intent are not
                      inferred.
                    </p>
                    <p className="quality">
                      <Video size={15} aria-hidden />
                      <span>
                        {incident.clip_actual_duration_seconds
                          ? `${incident.clip_actual_duration_seconds}s clip available. Source and annotated artifacts are preserved.`
                          : "Evidence incomplete. No clip was preserved."}
                      </span>
                    </p>
                    <div className="incident-actions">
                      {[
                        "AWAITING_HUMAN_DECISION",
                        "EVIDENCE_PREPARED",
                      ].includes(incident.status) && (
                        <button
                          className="button primary"
                          disabled={busy}
                          onClick={() => incidentAction("authorize-pickup")}
                        >
                          <Users size={15} aria-hidden />
                          Confirm authorized pickup
                        </button>
                      )}
                      {incident.status === "AWAITING_HUMAN_DECISION" && (
                        <button
                          className="button"
                          disabled={busy}
                          onClick={() => incidentAction("prepare-report")}
                        >
                          <FileCheck2 size={15} aria-hidden />
                          Review evidence / Prepare report
                        </button>
                      )}
                      {incident.status === "EVIDENCE_PREPARED" && (
                        <button
                          className="button"
                          disabled={busy}
                          onClick={() => setShowApproval(true)}
                        >
                          Review report
                          <ArrowRight size={15} aria-hidden />
                        </button>
                      )}
                      {incident.status === "REPORT_APPROVED" && (
                        <button
                          className="button primary"
                          disabled={busy}
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
                          disabled={busy}
                          onClick={() => incidentAction("cancel-report")}
                        >
                          Cancel report review
                        </button>
                      )}
                    </div>
                    <IncidentNext
                      status={incident.status}
                      onGo={(p) =>
                        p === "contracts"
                          ? navigate(
                              "contracts",
                              state.contracts.find((c) => c.key === "parcel") ??
                                null,
                            )
                          : navigate(p)
                      }
                    />
                    {incident.receipt && (
                      <div className="banner receipt" role="status">
                        <ShieldCheck size={15} aria-hidden />
                        <span>
                          <strong>Demo receiver — not sent to police</strong>
                          <code>{incident.receipt.receipt_id}</code>
                        </span>
                      </div>
                    )}
                  </section>
                  <section
                    className="panel packet"
                    aria-label="Evidence packet"
                  >
                    <div className="panel-head">
                      <h2>Evidence packet</h2>
                      <button
                        className="text-button"
                        onClick={() => navigate("evidence")}
                      >
                        All evidence <ArrowRight size={14} aria-hidden />
                      </button>
                    </div>
                    <div className="packet-body">
                      <div className="person-crop">
                        <img
                          src={
                            "/api/evidence/" +
                            incident.packet.person_crop_evidence_id
                          }
                          alt="Best available person crop"
                        />
                        <div>
                          <strong>Best available person crop</strong>
                          <small>No facial identification</small>
                        </div>
                      </div>
                      <dl className="facts">
                        <dt>Detected</dt>
                        <dd>{fmt(incident.detected_at)} IST</dd>
                        <dt>Location</dt>
                        <dd>Front porch</dd>
                        <dt>Coverage</dt>
                        <dd>{incident.clip_actual_duration_seconds}s clip</dd>
                        <dt>Source</dt>
                        <dd>{incidentSourceText}</dd>
                        <dt>Receiver</dt>
                        <dd>Demo receiver</dd>
                        <dt>Official dispatches</dt>
                        <dd>0 · not sent to police</dd>
                      </dl>
                      {incident.packet.source?.license && (
                        <p className="credit">
                          Footage: {incident.packet.source.title} ·{" "}
                          {incident.packet.source.author} ·{" "}
                          <a
                            href={incident.packet.source.license_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {incident.packet.source.license}
                          </a>
                        </p>
                      )}
                      {incident.packet.capture_gaps?.length > 0 && (
                        <ul className="gaps" aria-label="Capture gaps">
                          {incident.packet.capture_gaps.map((g) => (
                            <li key={g}>{plain(g)}</li>
                          ))}
                        </ul>
                      )}
                      <span className="eyebrow">SHA-256 manifest</span>
                      <code className="hash">{incident.manifest_hash}</code>
                      <p className="muted-text small">
                        A digest detects tampering; it does not establish legal
                        admissibility.
                      </p>
                      <a className="button wide" href="/api/export" download>
                        <Download size={15} aria-hidden />
                        Export verified manifest
                      </a>
                    </div>
                  </section>
                </div>
              ) : (
                <section className="panel fill">
                  <Empty icon={ShieldCheck} title="No incidents to review.">
                    <p>
                      A quiet porch. Run the deposit and removal scenes to see
                      evidence preservation and human review.
                    </p>
                    <div className="row">
                      {admin && (
                        <button
                          className="button small"
                          onClick={() => navigate("replay")}
                        >
                          Open judge replay <ArrowRight size={14} />
                        </button>
                      )}
                      <button
                        className="button small"
                        onClick={() => navigate("evidence")}
                      >
                        All evidence <ArrowRight size={14} />
                      </button>
                    </div>
                  </Empty>
                </section>
              ))}

            {page === "evidence" && (
              <section className="panel fill evidence-list">
                <div className="panel-head">
                  <h2>
                    Private evidence{" "}
                    <span className="count">{state.evidence.length}</span>
                  </h2>
                  <a className="button small" href="/api/export" download>
                    <Download size={14} aria-hidden />
                    Export verified manifest
                  </a>
                </div>
                <div className="scroll">
                  {state.evidence.length === 0 ? (
                    <Empty icon={FileCheck2} title="No evidence collected yet.">
                      <p>
                        Promises close only after their evidence policy is
                        satisfied.
                      </p>
                    </Empty>
                  ) : (
                    [...state.evidence].reverse().map((item) => (
                      <article className="evidence-row" key={item.evidence_id}>
                        <FileCheck2 size={18} aria-hidden />
                        <div>
                          <strong>{human(item.kind)}</strong>
                          <small>
                            {fmt(item.captured_at)} IST ·{" "}
                            {sourceWords(item.provenance)} ·{" "}
                            <code>{item.sha256_original.slice(0, 24)}…</code>
                          </small>
                        </div>
                        <a
                          className="text-button"
                          href={`/api/evidence/${item.evidence_id}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open <ArrowRight size={13} aria-hidden />
                        </a>
                      </article>
                    ))
                  )}
                </div>
              </section>
            )}

            {page === "settings" && (
              <div className="settings">
                <section className="panel" aria-label="Connections">
                  <div className="panel-head">
                    <h2>Connections</h2>
                    <Signal size={16} aria-hidden />
                  </div>
                  <p className="muted-text small pad">
                    Adapter code is not the same as a verified device.
                  </p>
                  <div className="scroll">
                    {integrations.map((it) => (
                      <div className="integration" key={it.name}>
                        <span className="integration-icon" aria-hidden>
                          {it.name === "Fire TV" ? (
                            <Tv size={16} />
                          ) : it.name === "Ring" ? (
                            <Video size={16} />
                          ) : it.name === "Bee" ? (
                            <AudioLines size={16} />
                          ) : (
                            <Radio size={16} />
                          )}
                        </span>
                        <div>
                          <strong>{it.name}</strong>
                          <p>{plain(it.reason)}</p>
                        </div>
                        <Status status={it.status} />
                      </div>
                    ))}
                  </div>
                </section>
                <div className="settings-stack">
                  <section className="panel consent" aria-label="Consent">
                    <div className="panel-head">
                      <h2>Consent</h2>
                      <Status status={state.consent ? "ACTIVE" : "PAUSED"} />
                    </div>
                    <p>
                      {live
                        ? "Your live household begins with collection disabled."
                        : "Demo day data stays in this workspace."}{" "}
                      Pausing stops compilation, camera processing and new
                      watchdog work.
                    </p>
                    <button
                      className={`button ${state.consent ? "" : "primary"}`}
                      disabled={busy}
                      onClick={() =>
                        void guarded(() =>
                          act("/consent", { enabled: !state.consent }),
                        )
                      }
                    >
                      {state.consent ? (
                        <Pause size={15} aria-hidden />
                      ) : (
                        <Play size={15} aria-hidden />
                      )}{" "}
                      {state.consent
                        ? "Pause all collection"
                        : live
                          ? "Enable household collection"
                          : "Restore demo consent"}
                    </button>
                    <ul className="facts-list">
                      <li>
                        <LockKeyhole size={14} aria-hidden /> Household-scoped
                        access
                      </li>
                      <li>
                        <Fingerprint size={14} aria-hidden /> SHA-256 artifact
                        integrity
                      </li>
                      <li>
                        <Users size={14} aria-hidden /> Human approval before
                        consequences
                      </li>
                      <li>
                        <Eye size={14} aria-hidden /> No secret-entry form in
                        the browser
                      </li>
                    </ul>
                  </section>
                  <PushOptIn act={act} busy={busy} />
                </div>
                <PrivacyControls act={act} busy={busy} />
              </div>
            )}
          </div>
        </main>
      </div>
      {!tv && (
        <nav className="bottom-nav" aria-label="Primary">
          {navPages.map((id) => {
            const Icon = pageIcons[id];
            const active =
              page === id || (id === "incidents" && page === "evidence");
            return (
              <button
                key={id}
                className={active ? "active" : ""}
                aria-current={active ? "page" : undefined}
                aria-label={pageLabel(id)}
                onClick={() => navigate(id)}
              >
                <Icon size={19} aria-hidden />
                <span aria-hidden>
                  {id === "overview" && !admin ? "Today" : short[id]}
                </span>
                {id === "incidents" && incident && <i aria-hidden />}
              </button>
            );
          })}
        </nav>
      )}
      {showNotifications && (
        <>
          <div
            className="scrim"
            aria-hidden
            onClick={() => setShowNotifications(false)}
          />
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Notifications"
          >
            <div className="panel-head">
              <h2>Your private inbox</h2>
              <button
                className="icon-button"
                aria-label="Close notifications"
                onClick={() => setShowNotifications(false)}
                autoFocus
              >
                <X size={17} aria-hidden />
              </button>
            </div>
            <p className="muted-text small pad">
              Companion inbox · native push and earbud whispers are not
              connected.
            </p>
            <div className="scroll">
              {[...state.alerts].reverse().map((a) => (
                <button
                  className="notification"
                  key={a.alert_id}
                  onClick={() => {
                    const c = state.contracts.find(
                      (c) => c.contract_id === a.contract_id,
                    );
                    if (c) goContract(c);
                    setShowNotifications(false);
                  }}
                >
                  <span className="kind" data-kind={a.kind}>
                    {human(a.kind)} · {fmt(a.at)}
                  </span>
                  <p>{plain(a.message)}</p>
                </button>
              ))}
              {!state.alerts.length && (
                <Empty icon={MessageSquareText} title="You’re all caught up." />
              )}
            </div>
          </aside>
        </>
      )}
      {showApproval && incident && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Approve report"
          >
            <button
              className="icon-button modal-close"
              aria-label="Close approval"
              onClick={() => setShowApproval(false)}
            >
              <X size={17} aria-hidden />
            </button>
            <span className="modal-icon" aria-hidden>
              <FileCheck2 size={22} />
            </span>
            <span className="eyebrow">Explicit owner approval</span>
            <h2>Review the exact packet.</h2>
            <p>
              This approves the report for the{" "}
              <strong>Demo receiver — not sent to police</strong>. No official
              case number is created.
            </p>
            <code className="hash">{incident.manifest_hash}</code>
            <p className="muted-text small">
              Coverage: {incident.clip_actual_duration_seconds}-second clip.
            </p>
            <label>
              Type APPROVE REPORT
              <input
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoFocus
                autoComplete="off"
              />
            </label>
            <button
              className="button primary wide"
              disabled={confirmation !== "APPROVE REPORT" || busy}
              onClick={() =>
                incidentAction("approve-report", {
                  confirmation,
                  destination: "DEMO_RECEIVER_ONLY",
                  manifest_hash: incident.manifest_hash,
                })
              }
            >
              Approve this packet
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
