import { useCallback, useEffect, useState } from "react";

/**
 * Medot Desktop — onboarding console.
 *
 * Flow: sign in with Google -> connect WhatsApp (paste the agent API key
 * from WhatsApp's Agent Manager) -> chat with Me. on WhatsApp.
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

type SessionState =
  | { status: "connecting" }
  | { status: "runtime_down" }
  | { status: "signed_out" }
  | { status: "signing_in" }
  | { status: "connect_whatsapp" }
  | { status: "connecting_whatsapp" }
  | { status: "ready"; user_id: string; connected_at: string | null };

export default function App() {
  const [state, setState] = useState<SessionState>({ status: "connecting" });
  const [error, setError] = useState("");
  const [apiKey, setApiKey] = useState("");

  const refresh = useCallback(async () => {
    try {
      const session = await api<{ authenticated: boolean; user_id?: string }>("/session");
      if (!session.authenticated) {
        setState({ status: "signed_out" });
        return;
      }
      const wa = await api<{ connected: boolean; connected_at: string | null }>("/whatsapp/status");
      if (!wa.connected) {
        setState({ status: "connect_whatsapp" });
        return;
      }
      setState({
        status: "ready",
        user_id: session.user_id!,
        connected_at: wa.connected_at,
      });
    } catch (err) {
      setError(String(err));
      setState({ status: "runtime_down" });
    }
  }, []);

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

  const connectWhatsapp = useCallback(async () => {
    setError("");
    setState({ status: "connecting_whatsapp" });
    try {
      await api("/whatsapp/connect", {
        method: "POST",
        body: JSON.stringify({ api_key: apiKey }),
      });
      setApiKey("");
      await refresh();
    } catch (err) {
      setError(String(err));
      setState({ status: "connect_whatsapp" });
    }
  }, [apiKey, refresh]);

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
              <li>Connect WhatsApp — paste your Medot agent key.</li>
            </ol>
            <button style={styles.primaryBtn} onClick={signIn}>
              Sign in with Google
            </button>
          </>
        )}

        {state.status === "signing_in" && (
          <p>Finish signing in with Google in your browser…</p>
        )}

        {state.status === "connect_whatsapp" && (
          <>
            <p style={styles.lede}>
              Last step — connect Medot to your WhatsApp.
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
              onKeyDown={(e) => e.key === "Enter" && apiKey && connectWhatsapp()}
            />
            {error && <p role="alert" style={styles.error}>{error}</p>}
            <button
              style={styles.primaryBtn}
              onClick={connectWhatsapp}
              disabled={!apiKey}
            >
              Connect WhatsApp
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
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    border: "1px solid #d6d3d1",
    borderRadius: 8,
    padding: "10px 12px",
    fontSize: 14,
    marginBottom: 8,
  },
  error: { color: "#b91c1c", fontSize: 13 },
  muted: { color: "#78716c", fontSize: 13 },
};
