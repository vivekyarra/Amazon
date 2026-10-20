import React, { useEffect, useState } from "react";
import { BellRing } from "lucide-react";

type Act = (path: string, body?: unknown) => Promise<unknown>;

function keyBytes(base64url: string) {
  const padded = base64url + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/** Companion surface (spec 5.3): standard Web Push to this browser/phone, owner-authenticated. */
export function PushOptIn({ act, busy }: { act: Act; busy: boolean }) {
  const supported =
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window;
  const [status, setStatus] = useState(supported ? "checking" : "unsupported");

  useEffect(() => {
    if (!supported) return;
    navigator.serviceWorker
      .getRegistration("/sw.js")
      .then((r) => r?.pushManager.getSubscription())
      .then((s) => setStatus(s ? "enabled" : "off"))
      .catch(() => setStatus("off"));
  }, [supported]);

  async function enable() {
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return setStatus("denied");
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const config = await (
        await fetch("/api/push/config", { credentials: "same-origin" })
      ).json();
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(config.public_key),
      });
      const json = sub.toJSON();
      await act("/push/subscribe", {
        endpoint: json.endpoint,
        keys: json.keys,
      });
      setStatus("enabled");
    } catch {
      setStatus("failed");
    }
  }

  async function disable() {
    const reg = await navigator.serviceWorker.getRegistration("/sw.js");
    const sub = await reg?.pushManager.getSubscription();
    if (sub) {
      await act("/push/unsubscribe", { endpoint: sub.endpoint });
      await sub.unsubscribe();
    }
    setStatus("off");
  }

  const label: Record<string, string> = {
    checking: "Checking…",
    unsupported:
      "This browser does not support Web Push (on iPhone, add to Home Screen first).",
    off: "Off — alerts stay in this app only.",
    enabled:
      "On — T-60/T-25, delivery, porch and arrival alerts reach this device.",
    denied: "Notifications were blocked in browser settings.",
    failed: "Could not enable push here. Alerts remain available in the app.",
  };

  return (
    <section className="panel" aria-labelledby="push-heading">
      <h2 id="push-heading">
        <BellRing size={18} aria-hidden /> Phone notifications
      </h2>
      <p>{label[status]}</p>
      <p className="muted">
        Lock-screen text is generic for porch and delivery incidents; evidence
        opens only after sign-in. &ldquo;Accepted by push service&rdquo; is
        recorded, never &ldquo;seen on device&rdquo;.
      </p>
      {status === "enabled" ? (
        <button type="button" disabled={busy} onClick={disable}>
          Turn off on this device
        </button>
      ) : (
        <button
          type="button"
          disabled={busy || !supported || status === "checking"}
          onClick={enable}
        >
          Enable phone notifications
        </button>
      )}
    </section>
  );
}
