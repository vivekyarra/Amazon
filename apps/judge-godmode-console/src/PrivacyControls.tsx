import React, { useCallback, useEffect, useState } from "react";
import { Camera, Clock3, PlugZap, Trash2 } from "lucide-react";
import "./privacy.css";
import { cameraName } from "./ui";

type ProviderStatus = { status: string; revoked_at?: string };
type Privacy = {
  household_id: string;
  cameras: string[];
  excluded_cameras: string[];
  masks: Record<
    string,
    { calibration_revision: number; polygons: number[][][] }
  >;
  retention_days: number;
  retention_bounds: [number, number];
  providers: Record<string, ProviderStatus>;
  deletion_receipts: { receipt_id: string; completed_at: string }[];
  delete_phrase: string;
  original_artifact_policy: string;
};

type Act = (path: string, body?: unknown) => Promise<unknown>;

/** Owner privacy controls (spec 12.1): exclusion, masks, retention, disconnect, delete. */
export function PrivacyControls({ act, busy }: { act: Act; busy: boolean }) {
  const [data, setData] = useState<Privacy | null>(null);
  const [days, setDays] = useState(7);
  const [maskCamera, setMaskCamera] = useState("");
  const [maskText, setMaskText] = useState("[]");
  const [phrase, setPhrase] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    const response = await fetch("/api/privacy", {
      credentials: "same-origin",
    });
    if (!response.ok) return;
    const d = (await response.json()) as Privacy;
    setData(d);
    setDays(d.retention_days);
    setMaskCamera((current) => current || d.cameras[0] || "");
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (data && maskCamera)
      setMaskText(JSON.stringify(data.masks[maskCamera]?.polygons ?? []));
  }, [data, maskCamera]);

  const run = async (path: string, body: unknown = {}) => {
    setNote("");
    try {
      await act(path, body);
    } catch {
      /* visible error is set by the console */
    }
    await load();
  };

  if (!data) return null;
  const [min, max] = data.retention_bounds;
  return (
    <section className="panel privacy-controls">
      <div className="panel-head">
        <h2>Privacy controls</h2>
        <span className="muted-text small">Audited · idempotent</span>
      </div>
      <div className="scroll">
        <div className="privacy-row">
          <Camera size={17} />
          <div>
            <strong>Cameras</strong>
            {data.cameras.length === 0 && <p>No linked cameras.</p>}
            {data.cameras.map((device) => {
              const excluded = data.excluded_cameras.includes(device);
              return (
                <div className="privacy-inline" key={device}>
                  <span>
                    {cameraName(device)} · {excluded ? "excluded" : "allowed"} ·
                    mask rev {data.masks[device]?.calibration_revision ?? 0}
                  </span>
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() =>
                      void run("/privacy/cameras/exclusion", {
                        device_id: device,
                        excluded: !excluded,
                      })
                    }
                  >
                    {excluded ? "Include" : "Exclude"}
                  </button>
                </div>
              );
            })}
            {data.cameras.length > 0 && (
              <form
                className="privacy-inline"
                onSubmit={(ev) => {
                  ev.preventDefault();
                  let polygons: unknown;
                  try {
                    polygons = JSON.parse(maskText);
                  } catch {
                    setNote("Masks must be JSON: [[[x, y], ...], ...] in 0–1.");
                    return;
                  }
                  void run("/privacy/cameras/masks", {
                    device_id: maskCamera,
                    polygons,
                    revision: data.masks[maskCamera]?.calibration_revision ?? 0,
                  });
                }}
              >
                <select
                  aria-label="Camera for masks"
                  value={maskCamera}
                  onChange={(ev) => setMaskCamera(ev.target.value)}
                >
                  {data.cameras.map((device) => (
                    <option key={device} value={device}>
                      {cameraName(device)}
                    </option>
                  ))}
                </select>
                <input
                  aria-label="PRIVATE_MASKS normalized polygons"
                  value={maskText}
                  onChange={(ev) => setMaskText(ev.target.value)}
                  maxLength={20000}
                />
                <button className="button" disabled={busy}>
                  Save masks
                </button>
              </form>
            )}
            <p>{data.original_artifact_policy}</p>
          </div>
        </div>

        <div className="privacy-row">
          <Clock3 size={17} />
          <form
            className="privacy-inline"
            onSubmit={(ev) => {
              ev.preventDefault();
              void run("/privacy/retention", { days });
            }}
          >
            <strong>Evidence retention</strong>
            <input
              aria-label="Retention days"
              type="number"
              min={min}
              max={max}
              value={days}
              onChange={(ev) => setDays(Number(ev.target.value))}
            />
            <span>days</span>
            <button className="button" disabled={busy}>
              Apply
            </button>
          </form>
        </div>

        <div className="privacy-row">
          <PlugZap size={17} />
          <div>
            <strong>Providers</strong>
            {Object.entries(data.providers).map(([name, provider]) => {
              const revoked = provider.status === "REVOKED";
              return (
                <div className="privacy-inline" key={name}>
                  <span>
                    {name} · {revoked ? "STANDBY (revoked)" : provider.status}
                  </span>
                  <button
                    className="button"
                    disabled={busy}
                    onClick={() =>
                      void run(
                        `/privacy/providers/${name}/${revoked ? "reauthorize" : "disconnect"}`,
                      )
                    }
                  >
                    {revoked ? "Re-authorize" : "Disconnect"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        <div className="privacy-row">
          <Trash2 size={17} />
          <form
            className="privacy-inline"
            onSubmit={(ev) => {
              ev.preventDefault();
              void run("/privacy/household/delete", {
                household_id: data.household_id,
                confirmation: phrase,
              }).then(() => setPhrase(""));
            }}
          >
            <strong>Delete household data</strong>
            <input
              aria-label="Deletion confirmation phrase"
              placeholder={data.delete_phrase}
              value={phrase}
              onChange={(ev) => setPhrase(ev.target.value)}
            />
            <button
              className="button"
              disabled={busy || phrase !== data.delete_phrase}
            >
              Delete
            </button>
          </form>
        </div>
        {data.deletion_receipts.map((receipt) => (
          <p className="muted" key={receipt.receipt_id}>
            Deletion receipt {receipt.receipt_id} · {receipt.completed_at}
          </p>
        ))}
        {note && <p className="muted">{note}</p>}
      </div>
    </section>
  );
}
