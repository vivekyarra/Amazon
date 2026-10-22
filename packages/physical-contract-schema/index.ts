export type SourceMode =
  "LIVE_VERIFIED" | "REPLAY_VERIFIED" | "STANDBY" | "BLOCKED";
export type ContractStatus =
  | "DISCOVERED"
  | "NEEDS_CONFIRMATION"
  | "ACTIVE"
  | "ENGAGED"
  | "EVIDENCE_PENDING"
  | "DISPUTED"
  | "MISSED"
  | "VERIFIED"
  | "CANCELLED"
  | "REJECTED";
export interface Contract {
  contract_id: string;
  key: string;
  title: string;
  status: ContractStatus;
  original_utterance: string;
  counterparty: { label: string };
  due_at: string | null;
  deadline_trigger: string | null;
  verification_modality: string;
  evidence_ids: string[];
  revision: number;
  source_mode: SourceMode;
  custody_status?: string;
  deposit_status?: string;
  visibility?: string;
  observation_status?: string;
  scheduled_jobs: { kind: string; at: string; status: string }[];
  recurrence?: { freq: string } | null;
  verification_note?: string;
  commitment_origin?: string;
  deadline_assumption?: string | null;
  scene_source?: { source: string };
  /** Set when VERIFIED: USER_CONFIRMED is an owner tap, never sensor proof (spec 4.3). */
  verification_provenance?: string;
  /** Another speaker proposed a new deadline; not applied until the owner acts. */
  proposed_amendment?: { due_at: string; source_event_id: string; at: string };
  target_reps?: number | null;
}
export interface LedgerEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  trace_id: string;
  source_mode: SourceMode;
  payload: Record<string, unknown>;
}
export interface Evidence {
  evidence_id: string;
  contract_id: string;
  kind: string;
  source_mode: SourceMode;
  provenance: string;
  sha256_original: string;
  chain_hash: string;
  mime: string;
  captured_at: string;
}
export interface Incident {
  incident_id: string;
  status: string;
  detected_at: string;
  manifest_hash: string;
  revision: number;
  clip_actual_duration_seconds: number;
  quality: string;
  packet: {
    removal_evidence_id: string;
    source_clip_evidence_id?: string;
    annotated_clip_evidence_id?: string;
    person_crop_evidence_id: string;
    source_frame_evidence_id?: string;
    annotated_frame_evidence_id?: string;
    source?: {
      label: string;
      title?: string;
      author?: string;
      license?: string;
      license_url?: string;
      page_url?: string;
    };
    capture_gaps: string[];
  };
  receipt: { label: string; receipt_id: string } | null;
}
export interface Studio {
  source?: string;
  source_mode?: SourceMode;
  last_timestamp_ms?: number;
  session_id: string;
  count: number;
  gate: string;
  status: string;
  phase: string;
  quality: string;
  angle: number;
  fixture_frame_index?: number;
  target_reps?: number;
}
export interface State {
  clock_mode?: "WALL" | "SCRIPTED";
  source_mode?: SourceMode;
  now: string;
  timezone: string;
  household_id: string;
  consent: boolean;
  contracts: Contract[];
  events: LedgerEvent[];
  alerts: {
    alert_id: string;
    kind: string;
    message: string;
    at: string;
    contract_id: string;
  }[];
  subagents: {
    subagent_id: string;
    kind: string;
    status: string;
    last_observation_at: string;
    contract_id: string;
  }[];
  evidence: Evidence[];
  incidents: Incident[];
  studio: Studio | null;
  scenario: number;
  failures: string[];
}
