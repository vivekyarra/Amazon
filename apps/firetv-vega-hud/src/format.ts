// Pure helpers that turn backend state into ten-foot labels.
// Every status is rendered as a word plus a glyph, never by color alone.

export type Json = any;

export const TERMINAL = new Set(['VERIFIED', 'REJECTED', 'CANCELLED', 'MISSED', 'EXPIRED']);

export function statusGlyph(status: string): string {
  switch (status) {
    case 'VERIFIED':
      return '[OK]';
    case 'MISSED':
    case 'DISPUTED':
    case 'FAILED':
      return '[!!]';
    case 'NEEDS_CONFIRMATION':
    case 'EVIDENCE_PENDING':
      return '[??]';
    case 'CANCELLED':
    case 'REJECTED':
      return '[--]';
    default:
      return '[..]';
  }
}

export function statusTone(status: string): 'ok' | 'bad' | 'warn' | 'neutral' {
  if (status === 'VERIFIED' || status === 'UNLOCKED' || status === 'AUTHORIZED_TRANSFER') {
    return 'ok';
  }
  if (status === 'MISSED' || status === 'DISPUTED' || status === 'AWAITING_HUMAN_DECISION') {
    return 'bad';
  }
  if (status === 'NEEDS_CONFIRMATION' || status === 'EVIDENCE_PENDING' || status === 'EVIDENCE_PREPARED') {
    return 'warn';
  }
  return 'neutral';
}

export function shortHash(h?: string | null, n = 12): string {
  if (!h) {
    return 'none';
  }
  return h.length > n ? h.slice(0, n) + '...' : h;
}

export function nowMs(state: Json, fetchedAt: number): number {
  const base = Date.parse(state && state.now);
  if (isNaN(base)) {
    return Date.now();
  }
  // Server clock is authoritative (VIRTUAL demo clock or WALL clock); advance it
  // locally only by real time elapsed since the snapshot was fetched.
  return base + (state.clock_mode === 'WALL' ? Date.now() - fetchedAt : 0);
}

export function countdown(dueAt: string | null | undefined, now: number): string {
  if (!dueAt) {
    return 'No clock deadline';
  }
  const due = Date.parse(dueAt);
  if (isNaN(due)) {
    return 'Unknown deadline';
  }
  let diff = Math.round((due - now) / 1000);
  const past = diff < 0;
  diff = Math.abs(diff);
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  const s = diff % 60;
  const txt = (h ? h + 'h ' : '') + m + 'm ' + (h ? '' : s + 's');
  return past ? 'Overdue by ' + txt.trim() : 'Due in ' + txt.trim();
}

export function deadlineLabel(c: Json, now: number): string {
  // A closed contract is never shown as "overdue".
  if (TERMINAL.has(c.status)) {
    return 'Closed (' + c.status + ')';
  }
  return countdown(c.due_at, now);
}

export function stageLabel(c: Json): string {
  const jobs: Json[] = c.scheduled_jobs || [];
  if (!jobs.length) {
    return c.deadline_trigger ? 'Trigger: ' + c.deadline_trigger : 'No escalation';
  }
  const parts = jobs
    .filter((j) => j.kind === 'T60' || j.kind === 'T25' || j.kind === 'DEADLINE')
    .map((j) => {
      const name = j.kind === 'T60' ? 'T-60' : j.kind === 'T25' ? 'T-25' : 'DUE';
      const st = j.status === 'EXECUTED' ? 'sent' : j.status === 'CANCELLED' ? 'cancelled' : 'pending';
      return name + ' ' + st;
    });
  return parts.join(' / ');
}

export function evidenceFor(state: Json, c: Json): Json[] {
  const ids = new Set(c.evidence_ids || []);
  return (state.evidence || []).filter((e: Json) => ids.has(e.evidence_id) || e.contract_id === c.contract_id);
}

export function evidenceStatus(state: Json, c: Json): string {
  const ev = evidenceFor(state, c);
  if (!ev.length) {
    return 'No evidence yet';
  }
  const last = ev[ev.length - 1];
  return ev.length + ' item' + (ev.length > 1 ? 's' : '') + ', last ' + last.kind + ' (' + (last.decision || 'recorded') + ')';
}

export function watchdogFor(state: Json, c: Json): Json | null {
  return (state.subagents || []).find((a: Json) => a.contract_id === c.contract_id) || null;
}

export function sourceLabel(mode?: string | null, platform?: string | null): string {
  const m = mode || '';
  const p = platform || '';
  if (p.indexOf('RING') >= 0 && m.indexOf('LIVE') >= 0) {
    return 'LIVE RING';
  }
  if (m.indexOf('SIMULATED') >= 0 || p.indexOf('SYNTHETIC') >= 0) {
    return 'Scripted replay';
  }
  if (m.indexOf('RECORDED') >= 0) {
    return 'Recorded workout';
  }
  if (m.indexOf('LIVE') >= 0) {
    return 'LIVE ' + (p || 'SOURCE');
  }
  return m || p || 'UNKNOWN SOURCE';
}

export function studioSourceLabel(studio: Json): string {
  const src = (studio && studio.source) || '';
  if (src.indexOf('LIVE_RING') >= 0) {
    return studio.source_mode === 'NOT_CONNECTED' ? 'LIVE RING (not connected)' : 'LIVE RING';
  }
  if (src.indexOf('RECORDED') >= 0) {
    return 'Recorded workout';
  }
  if (src.indexOf('SYNTHETIC') >= 0 || (studio && studio.source_mode === 'SIMULATED_VERIFIED')) {
    return 'Camera frames';
  }
  return src || 'UNKNOWN';
}

export function packetState(inc: Json): string {
  switch (inc && inc.status) {
    case 'EVIDENCE_PREPARED':
      return 'DRAFT';
    case 'REPORT_APPROVED':
      return 'APPROVED (not sent)';
    case 'SIMULATED_DISPATCH':
      return 'DEMO RECEIVER';
    case 'DISPATCHED':
      return 'DISPATCHED';
    case 'ACKNOWLEDGED':
      return 'ACKNOWLEDGED';
    case 'AUTHORIZED_TRANSFER':
      return 'CLOSED (authorized pickup)';
    default:
      return 'NOT PREPARED';
  }
}

export function timeLabel(iso?: string | null, tz?: string): string {
  if (!iso) {
    return '--';
  }
  const d = new Date(iso);
  if (isNaN(d.getTime())) {
    return iso;
  }
  try {
    return d.toLocaleString('en-GB', {
      timeZone: tz || 'UTC',
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: 'short',
    });
  } catch (e) {
    return iso.replace('T', ' ').slice(0, 16) + ' UTC';
  }
}

export function eventsFor(state: Json, cid: string): Json[] {
  return (state.events || []).filter((e: Json) => e.payload && e.payload.contract_id === cid);
}
