import React, {useCallback, useEffect, useRef, useState} from 'react';
import {AppState, BackHandler, Image, ScrollView, StyleSheet, Text, View} from 'react-native';
import {ApiError, DEFAULT_BACKEND, DoneIrlClient} from './api';
import {Badge, C, DpadKeyboard, FocusButton, Row, px} from './ui';
import {
  deadlineLabel,
  evidenceFor,
  evidenceStatus,
  eventsFor,
  nowMs,
  packetState,
  shortHash,
  sourceLabel,
  stageLabel,
  statusGlyph,
  statusTone,
  studioSourceLabel,
  TERMINAL,
  timeLabel,
  watchdogFor,
} from './format';

type Json = any;
const TABS = ['A  Commitments', 'B  Incident', 'C  Evidence', 'D  Reality-Lock'];
const POLL_MS = 3000;

export const App = () => {
  const clientRef = useRef<DoneIrlClient | null>(null);
  const [screen, setScreen] = useState<'login' | 'main'>('login');
  const [backend, setBackend] = useState(DEFAULT_BACKEND);
  const [username, setUsername] = useState('demo-admin');
  const [password, setPassword] = useState('');
  const [loginMsg, setLoginMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<null | 'backend' | 'username' | 'password'>(null);

  const [state, setState] = useState<Json>(null);
  const [fetchedAt, setFetchedAt] = useState(Date.now());
  const [online, setOnline] = useState(true);
  const [lastError, setLastError] = useState('');
  const [tvSession, setTvSession] = useState<string>('');
  const [integrations, setIntegrations] = useState<Json[]>([]);
  const [, setTick] = useState(0); // 1 s re-render for countdowns

  const [tab, setTab] = useState(0);
  const [detail, setDetail] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | {title: string; body: string; yes: string; run: () => Promise<void>}>(
    null,
  );
  const [actionMsg, setActionMsg] = useState('');
  const [frameOk, setFrameOk] = useState(true);
  const [showEntertainment, setShowEntertainment] = useState(false);

  // ---------- data ----------
  const refresh = useCallback(async () => {
    const cl = clientRef.current;
    if (!cl) {
      return;
    }
    try {
      const body = await cl.get('/api/state');
      setState(body.state);
      setFetchedAt(Date.now());
      setOnline(true);
      setLastError('');
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) {
        setScreen('login');
        setLoginMsg('Session expired. Sign in again.');
        return;
      }
      setOnline(false);
      setLastError(e && e.message ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (screen !== 'main') {
      return;
    }
    let active = AppState.currentState === 'active' || AppState.currentState == null;
    refresh();
    const iv = setInterval(() => {
      if (active) {
        refresh();
      }
    }, POLL_MS);
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    // Lifecycle: stop network polling while suspended, refresh immediately on resume.
    const sub = AppState.addEventListener('change', (st) => {
      active = st === 'active';
      if (active) {
        refresh();
      }
    });
    return () => {
      clearInterval(iv);
      clearInterval(t);
      sub && sub.remove && sub.remove();
    };
  }, [screen, refresh]);

  useEffect(() => {
    if (screen !== 'main' || !clientRef.current) {
      return;
    }
    clientRef.current
      .get('/api/integrations/status')
      .then((b) => setIntegrations((b && (b.providers || b.integrations)) || []))
      .catch(() => setIntegrations([]));
  }, [screen, online]);

  // ---------- back handling ----------
  useEffect(() => {
    const h = BackHandler.addEventListener('hardwareBackPress', () => {
      if (editing) {
        setEditing(null);
        return true;
      }
      if (confirm) {
        setConfirm(null);
        return true;
      }
      if (showEntertainment) {
        setShowEntertainment(false);
        return true;
      }
      if (detail) {
        setDetail(null);
        return true;
      }
      if (screen === 'main' && tab !== 0) {
        setTab(0);
        return true;
      }
      return false; // root: default behaviour exits the app
    });
    return () => h.remove();
  }, [editing, confirm, detail, screen, tab, showEntertainment]);

  // ---------- actions ----------
  const doLogin = async () => {
    setBusy(true);
    setLoginMsg('Signing in...');
    try {
      const cl = new DoneIrlClient(backend);
      await cl.login(username.trim(), password);
      clientRef.current = cl;
      setPassword('');
      try {
        const reg = await cl.post('/api/tv/sessions', {}, 'tv-session');
        const sess = reg && (reg.result || reg);
        setTvSession((sess && sess.session_id) || 'registered');
      } catch (e: any) {
        setTvSession('not registered: ' + (e.message || e));
      }
      const body = await cl.get('/api/state');
      setState(body.state);
      setFetchedAt(Date.now());
      setLoginMsg('');
      setScreen('main');
    } catch (e: any) {
      setLoginMsg('Sign-in failed: ' + (e && e.message ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  const run = async (label: string, path: string, body: Json) => {
    const cl = clientRef.current;
    if (!cl) {
      return;
    }
    setActionMsg(label + '...');
    try {
      await cl.post(path, body, label.replace(/\W+/g, '-').toLowerCase());
      setActionMsg(label + ': done (server confirmed)');
      await refresh();
    } catch (e: any) {
      setActionMsg(label + ' refused: ' + (e.code ? e.code + ' - ' : '') + e.message);
    }
  };

  const ask = (title: string, body: string, yes: string, fn: () => Promise<void>) =>
    setConfirm({title, body, yes, run: fn});

  // ---------- render helpers ----------
  if (screen === 'login' && editing) {
    const val = editing === 'backend' ? backend : editing === 'username' ? username : password;
    const set = editing === 'backend' ? setBackend : editing === 'username' ? setUsername : setPassword;
    return (
      <View style={st.root}>
        <DpadKeyboard
          title={editing === 'backend' ? 'Backend URL' : editing === 'username' ? 'Username' : 'Password'}
          value={val}
          secure={editing === 'password'}
          onChange={set}
          onDone={() => setEditing(null)}
        />
      </View>
    );
  }

  if (screen === 'login') {
    return (
      <View style={st.root}>
        <Text style={st.brand}>Muni</Text>
        <Text style={st.sub}>Fire TV command HUD - Vega OS</Text>
        <View style={st.loginBox}>
          <FocusButton
            testID="backend"
            label={'Backend URL: ' + backend}
            sub="OK to edit (on-screen keyboard)"
            onPress={() => setEditing('backend')}
          />
          <FocusButton
            testID="username"
            label={'Username: ' + username}
            sub="OK to edit"
            onPress={() => setEditing('username')}
          />
          <FocusButton
            testID="password"
            label={'Password: ' + (password ? password.replace(/./g, '*') : '(empty)')}
            sub="Typed on this TV with the remote; never stored in the app bundle"
            preferred
            onPress={() => setEditing('password')}
          />
          <FocusButton label={busy ? 'Signing in...' : 'Sign in'} onPress={doLogin} testID="signin" />
          {loginMsg ? <Text style={st.msg}>{loginMsg}</Text> : null}
        </View>
      </View>
    );
  }

  const now = nowMs(state, fetchedAt);
  const contracts: Json[] = (state && state.contracts) || [];
  const incident: Json = state && state.incidents && state.incidents[0];
  const studio: Json = state && state.studio;

  const header = (
    <View style={st.header}>
      <View style={st.headerMain}>
        <Text style={st.brandSmall}>Muni</Text>
        <Text style={st.meta}>
          {(clientRef.current && clientRef.current.user) || '?'} ({clientRef.current && clientRef.current.role}) -{' '}
          {state && state.household_id} - {state && state.source_mode} - clock {state && state.clock_mode}{' '}
          {timeLabel(state && state.now, state && state.timezone)}
        </Text>
        <Text style={st.meta}>
          TV session: {tvSession ? shortHash(tvSession, 18) : 'none'} - integrations:{' '}
          {integrations.length
            ? integrations.map((i: Json) => i.name + ' ' + i.status).join(', ')
            : 'status unavailable'}
        </Text>
      </View>
      <View style={st.netBox}>
        <Text style={[st.net, {color: online ? C.ok : C.bad}]}>
          {online ? 'ONLINE' : 'OFFLINE - retrying every 3 s'}
        </Text>
        <Text style={st.meta}>updated {Math.round((Date.now() - fetchedAt) / 1000)} s ago</Text>
      </View>
    </View>
  );

  const tabs = (
    <View style={st.tabs}>
      {TABS.map((t, i) => (
        <FocusButton
          key={t}
          testID={'tab' + i}
          label={(tab === i ? '[' : '') + t + (tab === i ? ']' : '')}
          preferred={i === tab && !detail}
          onPress={() => {
            setTab(i);
            setDetail(null);
            setActionMsg('');
          }}
          style={[st.tab, tab === i && st.tabActive]}
        />
      ))}
    </View>
  );

  // ---------- View A ----------
  const viewA = () => {
    if (detail) {
      const c = contracts.find((x) => x.contract_id === detail);
      if (!c) {
        return <Text style={st.body}>Contract no longer exists.</Text>;
      }
      const ev = evidenceFor(state, c);
      const last = ev[ev.length - 1];
      const wd = watchdogFor(state, c);
      const events = eventsFor(state, c.contract_id).slice(-14);
      const outstanding = TERMINAL.has(c.status)
        ? 'None - contract is ' + c.status
        : c.status === 'DISPUTED'
        ? 'Owner decision on the removal incident (View B)'
        : 'Awaiting ' + (c.required_evidence || []).join(', ');
      return (
        <ScrollView style={st.scroll}>
          <FocusButton label="Back to matrix" sub="or press Back on the remote" preferred onPress={() => setDetail(null)} />
          <Text style={st.h2}>
            {statusGlyph(c.status)} {c.title}
          </Text>
          <Badge label={c.status} tone={statusTone(c.status)} />
          <View style={st.card}>
            <Row k="Origin utterance" v={'"' + c.original_utterance + '"'} />
            <Row k="Actor" v={(c.actor && c.actor.role) + ' (' + (c.actor && c.actor.id) + ')'} />
            <Row k="Counterparty" v={(c.counterparty && c.counterparty.label) || '-'} />
            <Row k="Verification method" v={c.verification_modality} />
            <Row k="Deadline" v={deadlineLabel(c, now) + (c.due_at ? ' (' + timeLabel(c.due_at, c.timezone) + ')' : '')} />
            <Row k="Escalation" v={stageLabel(c)} />
            <Row
              k="Last evidence"
              v={
                last
                  ? last.kind + ' - ' + last.decision + ' - ' + timeLabel(last.captured_at, c.timezone) + ' - sha256 ' + shortHash(last.sha256_original)
                  : 'none'
              }
            />
            <Row k="Watcher" v={wd ? wd.kind + ' ' + wd.status : 'none'} />
            <Row k="Source" v={sourceLabel(c.source_mode, last && last.source_platform)} />
            <Row k="Outstanding action" v={outstanding} />
          </View>
          <Text style={st.h3}>Audit timeline ({events.length} most recent)</Text>
          {events.map((e: Json) => (
            <FocusButton key={e.event_id} label={timeLabel(e.occurred_at, c.timezone) + '  ' + e.event_type} sub={e.source + ' / ' + e.source_mode} style={st.timeline} />
          ))}
        </ScrollView>
      );
    }
    return (
      <ScrollView style={st.scroll}>
        <Text style={st.hint}>Up/Down to choose a contract, OK for details. Times use the server clock.</Text>
        {contracts.map((c, i) => {
          const wd = watchdogFor(state, c);
          return (
            <FocusButton key={c.contract_id} label={c.title + ', ' + c.status} testID={'contract' + i} onPress={() => setDetail(c.contract_id)} style={st.contract}>
              <View style={st.cRow}>
                <Badge label={statusGlyph(c.status) + ' ' + c.status} tone={statusTone(c.status)} />
                <Text style={st.cTitle}>{c.title}</Text>
              </View>
              <Text style={st.cLine}>
                {deadlineLabel(c, now)} - {stageLabel(c)}
              </Text>
              <Text style={st.cLine}>
                Evidence: {evidenceStatus(state, c)}
                {wd ? ' - ' + wd.kind + ': ' + wd.status : ''}
              </Text>
              <Text style={st.cSrc}>Source: {sourceLabel(c.source_mode)} - verify by {c.verification_modality}</Text>
            </FocusButton>
          );
        })}
      </ScrollView>
    );
  };

  // ---------- View B ----------
  const viewB = () => {
    if (!incident) {
      return (
        <View style={st.card}>
          <Text style={st.h2}>No removal incident</Text>
          <Text style={st.body}>PorchWatchdog has not reported a parcel removal. Nothing needs a decision.</Text>
        </View>
      );
    }
    const iid = incident.incident_id;
    const path = '/api/incidents/' + iid + '/';
    const status = incident.status;
    const pk = incident.packet || {};
    return (
      <ScrollView style={st.scroll}>
        <View style={st.cRow}>
          <Badge label={status} tone={statusTone(status)} />
          <Text style={st.h2}>Parcel removal intercept</Text>
        </View>
        <View style={st.card}>
          <Row k="Incident" v={iid + ' (rev ' + incident.revision + ')'} />
          <Row k="Detected" v={timeLabel(incident.detected_at, state.timezone)} />
          <Row k="Source" v={sourceLabel(incident.source_mode) + ' - ' + (incident.quality || '')} />
          <Row k="Clip" v={(incident.clip_actual_duration_seconds || 0) + ' s clip (evidence ' + shortHash(pk.source_clip_evidence_id, 14) + ')'} />
          <Row k="Movement" v={(pk.trajectory || []).map((p: number[]) => '(' + p.join(',') + ')').join(' -> ') + ' ' + (pk.coordinate_system || '')} />
          <Row k="Capture gaps" v={(pk.capture_gaps || []).join(' ') || 'none'} />
          <Row k="Destination" v={incident.destination || 'DEMO_RECEIVER_ONLY'} />
        </View>
        {status === 'AWAITING_HUMAN_DECISION' ? (
          <View style={st.btnRow}>
            <FocusButton
              testID="pickup"
              label="Confirm Authorized Pickup"
              sub="Opens a confirmation step"
              preferred
              onPress={() =>
                ask(
                  'Confirm authorized pickup?',
                  'You are stating that a family member or friend you authorized took the parcel. This is recorded as USER_CONFIRMED, not as identity verification.',
                  'Yes, it was authorized',
                  () => run('Authorized pickup', path + 'authorize-pickup', {action: 'authorize-pickup', revision: incident.revision}),
                )
              }
            />
            <FocusButton
              testID="review"
              label="Review / Prepare Report"
              sub="Draft only - nothing is sent"
              onPress={() => run('Prepare report draft', path + 'prepare-report', {action: 'prepare-report', revision: incident.revision})}
            />
          </View>
        ) : null}
        {status === 'EVIDENCE_PREPARED' ? (
          <View style={st.card}>
            <Text style={st.h3}>Human review - DRAFT (not sent)</Text>
            <Row k="Manifest SHA-256" v={shortHash(incident.manifest_hash, 32)} mono />
            <Row k="Attachments" v={'deposit, removal, clip, annotated clip, person crop'} />
            <Row k="Destination" v="Demo receiver - not sent to police" />
            <View style={st.btnRow}>
              <FocusButton label="Cancel review" preferred onPress={() => run('Cancel review', path + 'cancel-report', {action: 'cancel-report', revision: incident.revision})} />
              <FocusButton
                testID="approve"
                label="Approve report..."
                sub="Requires a separate confirmation"
                danger
                onPress={() =>
                  ask(
                    'Approve this exact report?',
                    'Manifest ' + shortHash(incident.manifest_hash, 24) + ' to DEMO_RECEIVER_ONLY. Approval does not send anything; dispatch is a further step.',
                    'APPROVE REPORT',
                    () =>
                      run('Approve report', path + 'approve-report', {
                        action: 'approve-report',
                        revision: incident.revision,
                        manifest_hash: incident.manifest_hash,
                        destination: 'DEMO_RECEIVER_ONLY',
                        confirmation: 'APPROVE REPORT',
                      }),
                  )
                }
              />
            </View>
          </View>
        ) : null}
        {status === 'REPORT_APPROVED' ? (
          <View style={st.btnRow}>
            <FocusButton label="Cancel report" preferred onPress={() => run('Cancel report', path + 'cancel-report', {action: 'cancel-report', revision: incident.revision})} />
            <FocusButton
              label="Send to DEMO receiver..."
              sub="Demo receiver - not sent to police"
              danger
              onPress={() =>
                ask(
                  'Send to demo receiver?',
                  'This sends the approved packet to the DEMO receiver only. No police or external party is contacted.',
                  'Send to demo receiver',
                  () => run('Demo dispatch', path + 'dispatch-report', {action: 'dispatch-report', revision: incident.revision}),
                )
              }
            />
          </View>
        ) : null}
        {status === 'SIMULATED_DISPATCH' || status === 'AUTHORIZED_TRANSFER' ? (
          <View style={st.card}>
            <Text style={st.h3}>Resolved: {packetState(incident)}</Text>
            {incident.receipt ? <Row k="Receipt" v={incident.receipt.label + ' - ' + incident.receipt.receipt_id} /> : null}
            <Row k="Official case ID" v={(incident.receipt && incident.receipt.official_case_id) || 'none (no external validated receipt)'} />
            <FocusButton label="Open evidence packet (View C)" preferred onPress={() => setTab(2)} />
          </View>
        ) : null}
      </ScrollView>
    );
  };

  // ---------- View C ----------
  const viewC = () => {
    const evidence: Json[] = (state && state.evidence) || [];
    const ps = packetState(incident);
    const states = ['DRAFT', 'DEMO RECEIVER', 'DISPATCHED', 'ACKNOWLEDGED'];
    return (
      <ScrollView style={st.scroll}>
        <View style={st.card}>
          <Text style={st.h3}>Packet state</Text>
          <View style={st.btnRow}>
            {states.map((x) => (
              <Text key={x} style={[st.state, ps.indexOf(x) === 0 && st.stateOn]}>
                {(ps.indexOf(x) === 0 ? '(*) ' : '( ) ') + x}
              </Text>
            ))}
          </View>
          <Row k="Current" v={ps} />
          {incident ? <Row k="Manifest SHA-256" v={shortHash(incident.manifest_hash, 40)} mono /> : null}
          {incident ? <Row k="Destination" v={incident.destination || '-'} /> : null}
          {incident && incident.approval ? (
            <Row k="Approval" v={incident.approval.owner + ' at ' + timeLabel(incident.approval.approved_at, state.timezone)} />
          ) : (
            <Row k="Approval" v="none recorded" />
          )}
          <Row k="Official case ID" v={(incident && incident.receipt && incident.receipt.official_case_id) || 'none - only an external validated receipt is a case ID'} />
        </View>
        <Text style={st.h3}>Evidence chain ({evidence.length})</Text>
        {evidence.map((e, i) => (
          <FocusButton key={e.evidence_id} label={e.kind + ', ' + (e.decision || 'recorded')} testID={'ev' + i} preferred={i === 0} style={st.contract}>
            <View style={st.cRow}>
              <Badge label={e.decision || 'RECORDED'} tone={e.decision === 'VALIDATED' ? 'ok' : 'neutral'} />
              <Text style={st.cTitle}>{e.kind}</Text>
            </View>
            <Text style={st.cLine}>
              {timeLabel(e.captured_at, state.timezone)} - {e.contract_id} - {e.mime}
            </Text>
            <Text style={[st.cLine, st.mono]}>sha256 {shortHash(e.sha256_original, 24)}  chain {shortHash(e.chain_hash, 16)}</Text>
            <Text style={st.cSrc}>
              Source: {sourceLabel(e.source_mode, e.source_platform)} - {e.source_platform} - provenance {e.provenance}
            </Text>
          </FocusButton>
        ))}
      </ScrollView>
    );
  };

  // ---------- View D ----------
  const viewD = () => {
    if (showEntertainment) {
      return (
        <View style={st.card}>
          <Text style={st.h2}>Entertainment unlocked</Text>
          <Text style={st.body}>
            The in-app gate is open because the backend reports gate {studio && studio.gate}. Muni does not control other apps.
          </Text>
          <FocusButton label="Back to studio" preferred onPress={() => setShowEntertainment(false)} />
        </View>
      );
    }
    if (!studio) {
      return (
        <View style={st.card}>
          <Text style={st.h2}>REALITY-LOCK studio</Text>
          <Text style={st.body}>No studio session yet. Rep count 0/15. Gate LOCKED.</Text>
          <FocusButton label="Start studio session" preferred onPress={() => run('Start studio', '/api/studio/sessions', {})} />
        </View>
      );
    }
    const count = Math.min(15, studio.count || 0);
    const unlocked = studio.gate === 'UNLOCKED';
    const override = studio.gate === 'USER_OVERRIDE';
    return (
      <View style={st.studio}>
        <View style={st.video}>
          {frameOk ? (
            <Image
              style={st.frame}
              resizeMode="contain"
              source={clientRef.current ? clientRef.current.frameSource('/api/studio/frame', studio.last_timestamp_ms || 0) : undefined}
              onError={() => setFrameOk(false)}
            />
          ) : (
            <Text style={st.body}>Annotated frame unavailable - counts below come from the backend verifier.</Text>
          )}
          <Text style={st.srcBanner}>SOURCE: {studioSourceLabel(studio)}</Text>
        </View>
        <ScrollView style={st.side}>
          <Text style={st.reps}>
            {count}/15
          </Text>
          <Text style={st.body}>verified reps</Text>
          <Badge
            label={unlocked ? '[OPEN] UNLOCKED' : override ? '[OVERRIDE] USER_OVERRIDE - not verified' : '[LOCKED] LOCKED'}
            tone={unlocked ? 'ok' : override ? 'warn' : 'bad'}
          />
          <Row k="Status" v={studio.status + ' / ' + studio.phase} />
          <Row k="Quality" v={studio.quality + ' - knee ' + Math.round(studio.angle || 0) + ' deg'} />
          <Row k="Source mode" v={studio.source_mode} />
          <FocusButton
            testID="continue"
            label="Continue to entertainment"
            sub={unlocked ? 'Gate UNLOCKED by backend verifier' : 'Locked until 15/15 verified'}
            disabled={!unlocked}
            preferred
            onPress={() => setShowEntertainment(true)}
          />
          {studio.status === 'RUNNING' ? (
            <FocusButton label="Pause" onPress={() => run('Pause', '/api/studio/control', {action: 'pause'})} />
          ) : null}
          {studio.status === 'PAUSED' ? (
            <FocusButton label="Resume" onPress={() => run('Resume', '/api/studio/control', {action: 'resume'})} />
          ) : null}
          {!unlocked && !override ? (
            <FocusButton
              label="Accessible override..."
              sub="Recorded as USER_OVERRIDE, never as verified"
              onPress={() =>
                ask(
                  'Use accessible override?',
                  'This opens entertainment without physical verification. It is recorded and labeled USER_OVERRIDE; the squat contract stays pending.',
                  'Record override',
                  () => run('Accessible override', '/api/studio/control', {action: 'accessible-override'}),
                )
              }
            />
          ) : null}
        </ScrollView>
      </View>
    );
  };

  const views = [viewA, viewB, viewC, viewD];

  return (
    <View style={st.root}>
      {header}
      {confirm ? null : tabs}
      {actionMsg ? <Text style={st.msg}>{actionMsg}</Text> : null}
      {!online && lastError ? <Text style={st.msg}>Network: {lastError}</Text> : null}
      {/* While a confirmation is open, the underlying view is not rendered so D-pad
          focus cannot leak to buttons behind the dialog. */}
      <View style={st.content}>
        {confirm ? null : state ? views[tab]() : <Text style={st.body}>Loading state...</Text>}
      </View>
      {confirm ? (
        <View style={st.overlay}>
          <View style={st.dialog}>
            <Text style={st.h2}>{confirm.title}</Text>
            <Text style={st.body}>{confirm.body}</Text>
            <View style={st.btnRow}>
              <FocusButton label="Cancel" preferred testID="confirm-cancel" onPress={() => setConfirm(null)} />
              <FocusButton
                label={confirm.yes}
                testID="confirm-yes"
                danger
                onPress={async () => {
                  const c = confirm;
                  setConfirm(null);
                  await c.run();
                }}
              />
            </View>
            <Text style={st.hint}>Focus starts on Cancel. Back also cancels.</Text>
          </View>
        </View>
      ) : null}
    </View>
  );
};

const st = StyleSheet.create({
  root: {flex: 1, backgroundColor: C.bg, paddingHorizontal: px(48), paddingVertical: px(28)},
  brand: {color: C.text, fontSize: px(72), fontWeight: '900', marginTop: px(40)},
  brandSmall: {color: C.text, fontSize: px(44), fontWeight: '900'},
  sub: {color: C.dim, fontSize: px(30), marginBottom: px(24)},
  loginBox: {width: px(1100), backgroundColor: C.panel, borderRadius: px(16), padding: px(32)},
  msg: {color: C.warn, fontSize: px(26), marginVertical: px(6)},
  header: {flexDirection: 'row', justifyContent: 'space-between'},
  headerMain: {flex: 1, marginRight: px(16)},
  meta: {color: C.dim, fontSize: px(22)},
  netBox: {alignItems: 'flex-end', width: px(330)},
  net: {fontSize: px(26), fontWeight: '800'},
  tabs: {flexDirection: 'row', marginVertical: px(8)},
  tab: {minWidth: px(330)},
  tabActive: {backgroundColor: '#22324A'},
  content: {flex: 1},
  scroll: {flex: 1},
  hint: {color: C.dim, fontSize: px(22), marginVertical: px(6)},
  contract: {paddingVertical: px(12)},
  cRow: {flexDirection: 'row', alignItems: 'center'},
  cTitle: {color: C.text, fontSize: px(32), fontWeight: '800'},
  cLine: {color: C.text, fontSize: px(24), marginTop: px(4)},
  cSrc: {color: C.dim, fontSize: px(22), marginTop: px(4)},
  mono: {fontFamily: 'monospace'},
  h2: {color: C.text, fontSize: px(38), fontWeight: '900', marginVertical: px(8)},
  h3: {color: C.text, fontSize: px(30), fontWeight: '800', marginVertical: px(8)},
  body: {color: C.text, fontSize: px(26), marginVertical: px(6)},
  card: {backgroundColor: C.panel, borderRadius: px(14), padding: px(20), marginVertical: px(8)},
  btnRow: {flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center'},
  timeline: {minHeight: px(56), paddingVertical: px(8)},
  state: {color: C.dim, fontSize: px(26), marginRight: px(28)},
  stateOn: {color: C.focus, fontWeight: '900'},
  studio: {flex: 1, flexDirection: 'row'},
  video: {flex: 3, backgroundColor: '#000', borderRadius: px(14), alignItems: 'center', justifyContent: 'center', marginRight: px(16)},
  frame: {width: '100%', height: '90%'},
  srcBanner: {color: C.focus, fontSize: px(26), fontWeight: '900', position: 'absolute', top: px(12), left: px(16)},
  side: {flex: 2},
  reps: {color: C.text, fontSize: px(120), fontWeight: '900'},
  overlay: {
    position: 'absolute',
    left: px(0),
    right: 0,
    top: px(0),
    bottom: 0,
    backgroundColor: C.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dialog: {width: px(1200), backgroundColor: C.panel, borderRadius: px(18), borderWidth: px(4), borderColor: C.warn, padding: px(32)},
});
