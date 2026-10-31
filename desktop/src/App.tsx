import { useCallback, useEffect, useState } from "react";

/**
 * Medot Desktop — Milestone 1 walking skeleton.
 *
 * Talks to the local runtime (127.0.0.1, launch-token auth). The launch token
 * arrives from the Tauri shell (read at startup from the sidecar's stdout).
 */

const RUNTIME_URL = "http://127.0.0.1:8756";

let launchToken = "";
export function setLaunchToken(token: string) {
  launchToken = token;
}

/** Complete sign-in when the shell forwards a medot://auth/callback URL. */
export async function completeDeepLink(url: string) {
  try {
    await api("/auth/callback", {
      method: "POST",
      body: JSON.stringify({ callback_url: url }),
    });
    // Deliver a state refresh to any mounted listener.
    window.dispatchEvent(new CustomEvent("medot:session-changed"));
  } catch (err) {
    console.error("deep-link sign-in failed", err);
  }
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

type SessionState =
  | { status: "connecting" }
  | { status: "runtime_down" }
  | { status: "signed_out" }
  | { status: "signing_in" }
  | { status: "signed_in"; user_id: string; complete: boolean; missing: string[] };

export default function App() {
  const [state, setState] = useState<SessionState>({ status: "connecting" });
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const session = await api<{
        authenticated: boolean;
        user_id?: string;
      }>("/session");
      if (!session.authenticated) {
        setState({ status: "signed_out" });
        return;
      }
      const boot = await api<{
        complete: boolean;
        missing: string[];
        me_identity_id: string;
      }>("/bootstrap");
      setState({
        status: "signed_in",
        user_id: session.user_id!,
        complete: boot.complete,
        missing: boot.missing,
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
      // The runtime completes sign-in when the deep-link callback arrives;
      // the shell forwards it. Poll for session restoration.
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const session = await api<{ authenticated: boolean; user_id?: string }>("/session");
        if (session.authenticated) break;
      }
      await refresh();
    } catch (err) {
      setError(String(err));
      setState({ status: "signed_out" });
    }
  }, [refresh]);

  return (
    <main style={styles.shell}>
      <header style={styles.header}>
        <h1 style={styles.wordmark}>
          Medot<span style={styles.dot}>.</span>
        </h1>
        <p style={styles.tagline}>Your personal companion</p>
      </header>

      <section style={styles.card}>
        {state.status === "connecting" && <p>Starting…</p>}
        {state.status === "runtime_down" && (
          <p role="alert">
            The Medot runtime is not reachable. {error}
          </p>
        )}
        {state.status === "signed_out" && (
          <>
            <p style={styles.lede}>
              Sign in with Google to create your personal space. Medot keeps
              your data in your own account, protected end to end.
            </p>
            <button style={styles.primaryBtn} onClick={signIn}>
              Sign in with Google
            </button>
          </>
        )}
        {state.status === "signing_in" && (
          <p>Finish signing in with Google in your browser…</p>
        )}
        {state.status === "signed_in" && (
          <>
            <p style={styles.lede}>
              Signed in. Me. is ready
              {state.complete
                ? " — your account is set up."
                : ` — account setup incomplete: ${state.missing.join(", ")}`}
            </p>
            <dl style={styles.facts}>
              <dt>User</dt>
              <dd style={styles.mono}>{state.user_id}</dd>
            </dl>
            <p style={styles.muted}>
              Next milestones add identities, WhatsApp connection and knowledge
              management here.
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
  primaryBtn: {
    background: "#1c1917",
    color: "#ffffff",
    border: "none",
    borderRadius: 8,
    padding: "10px 18px",
    fontSize: 15,
    cursor: "pointer",
  },
  facts: { display: "flex", gap: 8, alignItems: "baseline" },
  mono: { fontFamily: "ui-monospace, monospace", fontSize: 12, wordBreak: "break-all" },
  muted: { color: "#78716c", fontSize: 13 },
};
