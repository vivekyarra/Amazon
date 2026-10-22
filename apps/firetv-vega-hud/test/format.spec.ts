import {countdown, deadlineLabel, packetState, stageLabel, studioSourceLabel, statusGlyph} from '../src/format';
import {normalizeBase, idempotencyKey} from '../src/api';

describe('format helpers', () => {
  it('counts down against the server clock', () => {
    const now = Date.parse('2026-10-20T12:00:00Z');
    expect(countdown('2026-10-20T12:30:00Z', now)).toBe('Due in 30m 0s');
    expect(countdown('2026-10-20T11:00:00Z', now)).toBe('Overdue by 1h 0m');
    expect(countdown(null, now)).toBe('No clock deadline');
  });

  it('labels T-60/T-25 escalation stages', () => {
    const c = {
      scheduled_jobs: [
        {kind: 'T60', status: 'EXECUTED'},
        {kind: 'T25', status: 'PENDING'},
      ],
    };
    expect(stageLabel(c)).toBe('T-60 sent / T-25 pending');
  });

  it('never presents a local-receiver packet as dispatched', () => {
    expect(packetState({status: 'EVIDENCE_PREPARED'})).toBe('DRAFT');
    expect(packetState({status: 'LOCAL_DISPATCH'})).toBe('LOCAL RECEIVER');
    expect(packetState(null)).toBe('NOT PREPARED');
  });

  it('labels studio sources honestly', () => {
    expect(studioSourceLabel({source: 'SCRIPTED_MARKER_FRAMES'})).toBe('Camera frames');
    expect(studioSourceLabel({source: 'LIVE_RING_WHEP', source_mode: 'STANDBY'})).toBe(
      'LIVE RING (ready to link)',
    );
  });

  it('uses text glyphs, not only color', () => {
    expect(statusGlyph('VERIFIED')).toBe('[OK]');
    expect(statusGlyph('MISSED')).toBe('[!!]');
  });

  it('normalizes backend URLs and issues unique idempotency keys', () => {
    expect(normalizeBase('example.test/')).toBe('https://example.test');
    expect(idempotencyKey('a')).not.toBe(idempotencyKey('a'));
  });
});

describe('deadline labels', () => {
  it('never calls a closed contract overdue', () => {
    const now = Date.parse('2026-10-20T12:00:00Z');
    expect(deadlineLabel({status: 'VERIFIED', due_at: '2026-10-20T11:00:00Z'}, now)).toBe('Closed (VERIFIED)');
    expect(deadlineLabel({status: 'ACTIVE', due_at: '2026-10-20T11:00:00Z'}, now)).toBe('Overdue by 1h 0m');
  });
});
