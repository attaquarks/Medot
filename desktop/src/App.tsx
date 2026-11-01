import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Medot Desktop — onboarding console.
 *
 * Flow: sign in with Google -> connect WhatsApp -> chat with Me. on WhatsApp.
 * WhatsApp supports two routes (docs/medot/03, decision 2026-11-02):
 *   • Official Agent Platform — paste the agent API key from WhatsApp.
 *   • Baileys bridge (unofficial) — scan a QR like WhatsApp Web.
 * Either or both can be connected at the same time.
 * Talks to the local runtime (127.0.0.1, launch-token auth).
 */

const RUNTIME_URL = "http://127.0.0.1:8756";

let launchToken = "";
export function setLaunchToken(token: string) {
  launchToken = token;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${RUNTIME_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Launch-Token": launchToken,
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

/** Complete sign-in when the shell forwards a medot://auth/callback URL. */
export async function completeDeepLink(url: string) {
  try {
    await api("/auth/callback", {
      method: "POST",
      body: JSON.stringify({ callback_url: url }),
    });
    window.dispatchEvent(new CustomEvent("medot:session-changed"));
  } catch (err) {
    console.error("deep-link sign-in failed", err);
  }
}

type RouteStatus = {
  transport: string;
  connected?: boolean;
  running?: boolean;
  error?: string | null;
  connected_at?: string | null;
};

type WaStatus = {
  agent_platform: RouteStatus;
  baileys: RouteStatus;
  any_connected: boolean;
};

type SessionState =
  | { status: "connecting" }
  | { status: "runtime_down" }
  | { status: "signed_out" }
  | { status: "signing_in" }
  | { status: "connect_whatsapp" }
  | { status: "connecting_whatsapp" }
  | { status: "ready"; user_id?: string };

export default function App() {
  const [state, setState] = useState<SessionState>({ status: "connecting" });
  const [error, setError] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [waStatus, setWaStatus] = useState<WaStatus | null>(null);
  const [route, setRoute] = useState<"choice" | "agent_platform" | "baileys">("choice");
  const [baileysMode, setBaileysMode] = useState<"self" | "bot">("self");
  const [qr, setQr] = useState<string | null>(null);
  const [baileysPaired, setBaileysPaired] = useState(false);
  const qrPolling = useRef(false);

  const refreshWaStatus = useCallback(async () => {
    const s = await api<WaStatus>("/whatsapp/status");
    setWaStatus(s);
    return s;
  }, []);

  const refresh = useCallback(async () => {
    try {
      const session = await api<{ authenticated: boolean; user_id?: string }>("/session");
      if (!session.authenticated) {
        setState({ status: "signed_out" });
        return;
      }
      const s = await refreshWaStatus();
      setState({ status: s.any_connected ? "ready" : "connect_whatsapp", user_id: session.user_id! });
    } catch (err) {
      setError(String(err));
      setState({ status: "runtime_down" });
    }
  }, [refreshWaStatus]);

  useEffect(() => {
    refresh();
    window.addEventListener("medot:session-changed", refresh);
    return () => window.removeEventListener("medot:session-changed", refresh);
  }, [refresh]);

  const signIn = useCallback(async () => {
    setState({ status: "signing_in" });
    try {
      await api("/auth/start", { method: "POST" });
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const session = await api<{ authenticated: boolean }>("/session");
        if (session.authenticated) break;
      }
      await refresh();
    } catch (err) {
      setError(String(err));
      setState({ status: "signed_out" });
    }
  }, [refresh]);

  // ---- Route 1: official Agent Platform ----------------------------------
  const connectAgentPlatform = useCallback(async () => {
    setError("");
    setState({ status: "connecting_whatsapp" });
    try {
      await api("/whatsapp/agent-platform/connect", {
        method: "POST",
        body: JSON.stringify({ api_key: apiKey }),
      });
      setApiKey("");
      const s = await refreshWaStatus();
      setState({ status: s.any_connected ? "ready" : "connect_whatsapp" });
    } catch (err) {
      setError(String(err));
      setState({ status: "connect_whatsapp" });
    }
  }, [apiKey, refreshWaStatus]);

  // ---- Route 2: Baileys bridge -------------------------------------------
  const connectBaileys = useCallback(async () => {
    setError("");
    setState({ status: "connecting_whatsapp" });
    try {
      await api("/whatsapp/baileys/connect", {
        method: "POST",
        body: JSON.stringify({ mode: baileysMode }),
      });
      // Poll for the QR until paired (QRs refresh ~20 s on WhatsApp's side).
      qrPolling.current = true;
      for (let i = 0; i < 300 && qrPolling.current; i++) {
        const { qr: newQr, paired } = await api<{ qr: string | null; paired: boolean }>(
          "/whatsapp/baileys/qr",
        );
        setQr(newQr);
        setBaileysPaired(paired);
        if (paired) {
          const s = await refreshWaStatus();
          setState({ status: s.any_connected ? "ready" : "connect_whatsapp" });
          break;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    } catch (err) {
      setError(String(err));
      setState({ status: "connect_whatsapp" });
    } finally {
      qrPolling.current = false;
    }
  }, [baileysMode, refreshWaStatus]);

  const disconnect = useCallback(
    async (which: "agent-platform" | "baileys") => {
      setError("");
      try {
        await api(`/whatsapp/${which}/disconnect`, { method: "POST" });
        const s = await refreshWaStatus();
        setState({ status: s.any_connected ? "ready" : "connect_whatsapp" });
      } catch (err) {
        setError(String(err));
      }
    },
    [refreshWaStatus],
  );

  const routeBadge = (s: RouteStatus | undefined) => {
    if (!s?.connected) return <span style={styles.badgeOff}>Not connected</span>;
    if (s.error) return <span style={styles.badgeWarn}>Error: {s.error}</span>;
    return <span style={styles.badgeOn}>Connected</span>;
  };

  return (
    <main style={styles.shell}>
      <header style={styles.header}>
        <h1 style={styles.wordmark}>
          Medot<span style={styles.dot}>.</span>
        </h1>
        <p style={styles.tagline}>Your personal companion — on WhatsApp</p>
      </header>

      <section style={styles.card}>
        {state.status === "connecting" && <p>Starting…</p>}

        {state.status === "runtime_down" && (
          <p role="alert">The Medot runtime is not reachable. {error}</p>
        )}

        {state.status === "signed_out" && (
          <>
            <p style={styles.lede}>
              Two quick steps and you're talking with Me. on WhatsApp:
            </p>
            <ol style={styles.steps}>
              <li>Sign in with Google — creates your personal space.</li>
              <li>Connect WhatsApp — official API or QR scan, your choice.</li>
            </ol>
            <button style={styles.primaryBtn} onClick={signIn}>
              Sign in with Google
            </button>
          </>
        )}

        {state.status === "signing_in" && (
          <p>Finish signing in with Google in your browser…</p>
        )}

        {state.status === "connect_whatsapp" && route === "choice" && (
          <>
            <p style={styles.lede}>Connect Medot to WhatsApp — pick a route:</p>
            <button style={styles.routeCard} onClick={() => setRoute("agent_platform")}>
              <strong>Official — WhatsApp Agent Platform</strong>
              <span style={styles.routeDesc}>
                Create the Medot agent in WhatsApp's Agent Manager and paste its
                API key. No extra software. Official, no ban risk.
              </span>
            </button>
            <button style={styles.routeCard} onClick={() => setRoute("baileys")}>
              <strong>QR scan — Baileys bridge (unofficial)</strong>
              <span style={styles.routeDesc}>
                Pair like WhatsApp Web. Needs Node.js 18+. Supports groups and a
                dedicated bot number — small ban risk, use a secondary number.
              </span>
            </button>
            {waStatus && (
              <p style={styles.muted}>
                Agent Platform: {routeBadge(waStatus.agent_platform)} · Baileys:{" "}
                {routeBadge(waStatus.baileys)}
              </p>
            )}
          </>
        )}

        {state.status === "connect_whatsapp" && route === "agent_platform" && (
          <>
            <p style={styles.lede}>
              Official route — connect your Medot agent.
            </p>
            <ol style={styles.steps}>
              <li>
                Open <strong>WhatsApp → Settings → Agents</strong> and create
                the <strong>Medot</strong> agent.
              </li>
              <li>
                WhatsApp shows you an <strong>API key</strong> — copy it.
              </li>
              <li>Paste it below. It stays on this computer, encrypted.</li>
            </ol>
            <input
              style={styles.input}
              type="password"
              placeholder="Paste your WhatsApp agent API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && apiKey && connectAgentPlatform()}
            />
            {error && <p role="alert" style={styles.error}>{error}</p>}
            <button
              style={styles.primaryBtn}
              onClick={connectAgentPlatform}
              disabled={!apiKey}
            >
              Connect Agent Platform
            </button>
            <button style={styles.secondaryBtn} onClick={() => setRoute("choice")}>
              ← Other routes
            </button>
          </>
        )}

        {state.status === "connect_whatsapp" && route === "baileys" && (
          <>
            <p style={styles.lede}>QR route — pair like WhatsApp Web.</p>
            <div style={styles.modeRow}>
              <label style={styles.radio}>
                <input
                  type="radio"
                  checked={baileysMode === "self"}
                  onChange={() => setBaileysMode("self")}
                />
                My own number (message yourself)
              </label>
              <label style={styles.radio}>
                <input
                  type="radio"
                  checked={baileysMode === "bot"}
                  onChange={() => setBaileysMode("bot")}
                />
                Dedicated bot number
              </label>
            </div>
            <ol style={styles.steps}>
              <li>Open <strong>WhatsApp → Settings → Linked Devices</strong>.</li>
              <li>Tap <strong>Link a Device</strong> and scan the QR.</li>
            </ol>
            {qr && (
              <p style={{ textAlign: "center" }}>
                <img src={qr} alt="WhatsApp pairing QR code" style={styles.qr} />
              </p>
            )}
            {baileysPaired && <p style={styles.ok}>✅ Paired.</p>}
            {error && <p role="alert" style={styles.error}>{error}</p>}
            <button style={styles.primaryBtn} onClick={connectBaileys}>
              {qr ? "Regenerate QR" : "Show QR"}
            </button>
            <button style={styles.secondaryBtn} onClick={() => setRoute("choice")}>
              ← Other routes
            </button>
          </>
        )}

        {state.status === "connecting_whatsapp" && <p>Connecting…</p>}

        {state.status === "ready" && (
          <>
            <p style={styles.lede}>
              ✅ All set. Open <strong>WhatsApp</strong> and start chatting with
              your Medot agent — Me. is listening there.
            </p>
            <div style={styles.statusRow}>
              <span>Agent Platform {routeBadge(waStatus?.agent_platform)}</span>
              <button
                style={styles.linkBtn}
                onClick={() => disconnect("agent-platform")}
              >
                disconnect
              </button>
            </div>
            <div style={styles.statusRow}>
              <span>Baileys {routeBadge(waStatus?.baileys)}</span>
              <button style={styles.linkBtn} onClick={() => disconnect("baileys")}>
                disconnect
              </button>
            </div>
            <p style={styles.muted}>
              Connect the other route any time to run both simultaneously.
            </p>
            <button style={styles.secondaryBtn} onClick={() => setRoute("choice")}>
              + Connect another route
            </button>
            <p style={styles.muted}>
              Me. learns about you as you chat, and your specialist identities
              (Health, Education, …) will appear here as they develop.
            </p>
          </>
        )}
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  shell: {
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
    minHeight: "100vh",
    margin: 0,
    padding: "48px 32px",
    background: "#fafaf9",
    color: "#1c1917",
    boxSizing: "border-box",
  },
  header: { maxWidth: 560, margin: "0 auto 24px" },
  wordmark: { fontSize: 28, fontWeight: 650, margin: 0, letterSpacing: "-0.02em" },
  dot: { color: "#d97706" },
  tagline: { margin: "4px 0 0", color: "#78716c", fontSize: 14 },
  card: {
    maxWidth: 560,
    margin: "0 auto",
    background: "#ffffff",
    border: "1px solid #e7e5e4",
    borderRadius: 12,
    padding: 24,
  },
  lede: { marginTop: 0, lineHeight: 1.5 },
  steps: { lineHeight: 1.7, paddingLeft: 20 },
  primaryBtn: {
    background: "#1c1917",
    color: "#ffffff",
    border: "none",
    borderRadius: 8,
    padding: "10px 18px",
    fontSize: 15,
    cursor: "pointer",
    marginTop: 8,
    marginRight: 8,
  },
  secondaryBtn: {
    background: "transparent",
    color: "#1c1917",
    border: "1px solid #d6d3d1",
    borderRadius: 8,
    padding: "10px 18px",
    fontSize: 14,
    cursor: "pointer",
    marginTop: 8,
  },
  linkBtn: {
    background: "transparent",
    color: "#b91c1c",
    border: "none",
    fontSize: 12,
    cursor: "pointer",
    textDecoration: "underline",
  },
  routeCard: {
    display: "block",
    width: "100%",
    textAlign: "left",
    background: "#fafaf9",
    border: "1px solid #d6d3d1",
    borderRadius: 10,
    padding: "14px 16px",
    margin: "10px 0",
    cursor: "pointer",
    font: "inherit",
  },
  routeDesc: { display: "block", marginTop: 4, color: "#78716c", fontSize: 13 },
  modeRow: { display: "flex", gap: 16, margin: "8px 0" },
  radio: { fontSize: 14, display: "flex", alignItems: "center", gap: 6 },
  qr: { width: 240, height: 240, borderRadius: 8 },
  ok: { color: "#15803d", fontSize: 14 },
  input: {
    width: "100%",
    boxSizing: "border-box",
    border: "1px solid #d6d3d1",
    borderRadius: 8,
    padding: "10px 12px",
    fontSize: 14,
    marginBottom: 8,
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottom: "1px solid #f0efee",
    padding: "8px 0",
    fontSize: 14,
  },
  badgeOn: { color: "#15803d", fontWeight: 600, marginLeft: 4 },
  badgeOff: { color: "#a8a29e", marginLeft: 4 },
  badgeWarn: { color: "#b45309", marginLeft: 4 },
  error: { color: "#b91c1c", fontSize: 13 },
  muted: { color: "#78716c", fontSize: 13 },
};
