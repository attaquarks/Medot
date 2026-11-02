import { useCallback, useEffect, useState } from "react";
import { api, type WaStatus } from "./lib/api";

type SignInProps = { onSignIn: () => void; busy?: boolean; error?: string };

export function SignIn({ onSignIn, busy, error }: SignInProps) {
  return (
    <div className="centered">
      <div className="sheet">
        <div className="wordmark">Medot<span className="dot">.</span></div>
        <h1>Your companion's first page</h1>
        <p>Two quick steps and you're talking with Me. on WhatsApp:</p>
        <ol>
          <li>Sign in with Google — it creates your personal space.</li>
          <li>Connect WhatsApp — official API or QR scan, your choice.</li>
        </ol>
        <button className="btn" type="button" onClick={onSignIn} disabled={busy}>
          {busy ? "Waiting for Google…" : "Sign in with Google"}
        </button>
        {error && <p role="alert" className="error">{error}</p>}
        <p className="muted">
          Your data lives in your own private space — this computer and your
          own database. Nothing is shared.
        </p>
      </div>
    </div>
  );
}

type ConnectProps = { onDone: () => void };

export function ConnectWhatsApp({ onDone }: ConnectProps) {
  const [route, setRoute] = useState<"choice" | "agent_platform" | "baileys">("choice");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [qr, setQr] = useState<string | null>(null);
  const [paired, setPaired] = useState(false);

  const refreshWa = useCallback(async () => {
    const s = await api<WaStatus>("/whatsapp/status");
    return s;
  }, []);

  useEffect(() => {
    if (route !== "baileys") return;
    let live = true;
    (async () => {
      while (live) {
        try {
          const r = await api<{ qr: string | null; paired: boolean }>("/whatsapp/baileys/qr");
          if (!live) return;
          setQr(r.qr);
          setPaired(r.paired);
          if (r.paired) break;
        } catch {
          if (!live) return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    })();
    return () => { live = false; };
  }, [route]);

  const connectAP = useCallback(async () => {
    setError("");
    try {
      await api("/whatsapp/agent-platform/connect", {
        method: "POST",
        body: JSON.stringify({ api_key: apiKey }),
      });
      setApiKey("");
      const s = await refreshWa();
      if (s.any_connected) onDone();
    } catch (err) {
      setError(String(err));
    }
  }, [apiKey, refreshWa, onDone]);

  const startBaileys = useCallback(async () => {
    setError("");
    try {
      await api("/whatsapp/baileys/connect", {
        method: "POST",
        body: JSON.stringify({ mode: "self" }),
      });
    } catch (err) {
      setError(String(err));
    }
  }, []);


  return (
    <div className="centered">
      <div className="sheet">
        <div className="wordmark">Medot<span className="dot">.</span></div>
        {route === "choice" && (
          <>
            <h1>Connect WhatsApp</h1>
            <p>Pick a route — either, or both:</p>
            <button className="route-choice" type="button" onClick={() => setRoute("agent_platform")}>
              <strong>Official — WhatsApp Agent Platform</strong>
              <span>Create the Medot agent in WhatsApp's Agent Manager and paste its API key. Official, no extra software.</span>
            </button>
            <button className="route-choice" type="button" onClick={() => setRoute("baileys")}>
              <strong>QR scan — Baileys bridge (unofficial)</strong>
              <span>Pair like WhatsApp Web. Needs Node.js 18+. Small ban risk — a dedicated number is safest.</span>
            </button>
            {error && <p role="alert" className="error">{error}</p>}
            <button className="link back-link" type="button" onClick={onDone}>Skip for now</button>
          </>
        )}

        {route === "agent_platform" && (
          <>
            <h1>Official route</h1>
            <p>Create the Medot agent in WhatsApp and paste its API key.</p>
            <ol>
              <li>Open <strong>WhatsApp → Settings → Agents</strong> and create the <strong>Medot</strong> agent.</li>
              <li>WhatsApp shows you an <strong>API key</strong> — copy it.</li>
              <li>Paste it below. It stays on this computer, encrypted.</li>
            </ol>
            <label className="field-label" htmlFor="wa-key">Agent API key</label>
            <input id="wa-key" type="password" placeholder="Paste your WhatsApp agent API key"
                   value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && apiKey && connectAP()} />
            {error && <p role="alert" className="error">{error}</p>}
            <p style={{ marginTop: 14 }}>
              <button className="btn" type="button" onClick={connectAP} disabled={!apiKey}>Connect</button>
              {" "}
              <button className="btn-ghost" type="button" onClick={() => setRoute("choice")}>Other routes</button>
            </p>
          </>
        )}

        {route === "baileys" && (
          <>
            <h1>QR route</h1>
            <p>Pair like WhatsApp Web — scan with your phone.</p>
            <p className="entry-sub">For now you pair your own number — dedicated bot numbers arrive later.</p>
            <ol>
              <li>Open <strong>WhatsApp → Settings → Linked Devices</strong>.</li>
              <li>Tap <strong>Link a Device</strong> and scan the QR below.</li>
            </ol>
            {(qr || paired) && (
              <div className="qr-wrap">
                {paired
                  ? <p className="ok-note">Paired — Me. is listening on WhatsApp.</p>
                  : qr && <img src={qr} alt="WhatsApp pairing QR code" />}
              </div>
            )}
            {error && <p role="alert" className="error">{error}</p>}
            <p style={{ marginTop: 14 }}>
              <button className="btn" type="button" onClick={startBaileys}>{qr ? "Regenerate QR" : "Show QR"}</button>
              {" "}
              <button className="btn-ghost" type="button" onClick={() => setRoute("choice")}>Other routes</button>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
