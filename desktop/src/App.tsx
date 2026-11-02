import { useCallback, useEffect, useState } from "react";
import { api, type Session, type WaStatus } from "./lib/api";
import { SignIn, ConnectWhatsApp } from "./screens-onboarding";
import {
  Overview, Identities, Knowledge, Connectors, Providers, Activity, Settings,
} from "./screens-console";
import "./styles/console.css";

type Phase = "connecting" | "runtime_down" | "signed_out" | "onboarding" | "console";

const PAGES = [
  "Overview", "Identities", "Knowledge", "Connectors",
  "AI Providers", "Activity", "Settings",
] as const;
type Page = (typeof PAGES)[number];

export default function App() {
  const [phase, setPhase] = useState<Phase>("connecting");
  const [page, setPage] = useState<Page>("Overview");
  const [error, setError] = useState("");
  const [wa, setWa] = useState<WaStatus | null>(null);
  const [user, setUser] = useState<Session | null>(null);
  const [signingIn, setSigningIn] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const session = await api<Session>("/session");
      if (!session.authenticated) {
        setUser(null);
        setPhase("signed_out");
        return;
      }
      setUser(session);
      const status = await api<WaStatus>("/whatsapp/status");
      setWa(status);
      setPhase(status.any_connected ? "console" : "onboarding");
    } catch (err) {
      setError(String(err));
      setPhase("runtime_down");
    }
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("medot:session-changed", refresh);
    return () => window.removeEventListener("medot:session-changed", refresh);
  }, [refresh]);

  const signIn = useCallback(async () => {
    setError("");
    setSigningIn(true);
    try {
      await api("/auth/start", { method: "POST" });
      let signedIn = false;
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const session = await api<Session>("/session");
        if (session.authenticated) {
          signedIn = true;
          break;
        }
      }
      if (!signedIn) {
        setError("Google sign-in didn't finish in your browser. Try again — it usually works on the second go.");
      }
      await refresh();
    } catch (err) {
      console.error(err);
      setError("Couldn't reach the sign-in flow. Make sure Medot is running, then try again.");
      setPhase("signed_out");
    } finally {
      setSigningIn(false);
    }
  }, [refresh]);

  const signOut = useCallback(async () => {
    try {
      await api("/session/signout", { method: "POST" });
    } catch {
      /* session already gone */
    }
    setUser(null);
    setWa(null);
    setPhase("signed_out");
  }, []);

  const onboarded = useCallback(() => {
    setPhase("console");
    refresh();
  }, [refresh]);

  if (phase === "signed_out") {
    return <SignIn onSignIn={signIn} busy={signingIn} error={error} />;
  }

  if (phase === "onboarding") {
    return <ConnectWhatsApp onDone={onboarded} />;
  }

  if (phase === "connecting") {
    return (
      <div className="centered">
        <div className="sheet">
          <div className="wordmark">Medot<span className="dot">.</span></div>
          <p>Opening your day-runner…</p>
        </div>
      </div>
    );
  }

  if (phase === "runtime_down") {
    return (
      <div className="centered">
        <div className="sheet">
          <div className="wordmark">Medot<span className="dot">.</span></div>
          <p role="alert">Medot's engine isn't answering. It usually starts on its own — give it a moment.</p>
          <p className="muted">
            Keep this window open. If it stays down, quit Medot from the tray
            and start it again.
          </p>
        </div>
      </div>
    );
  }

  const renderPage = () => {
    switch (page) {
      case "Overview": return <Overview wa={wa} onConnect={() => setPhase("onboarding")} go={setPage} />;
      case "Identities": return <Identities wa={wa} user={user} />;
      case "Knowledge": return <Knowledge wa={wa} user={user} />;
      case "Connectors": return <Connectors wa={wa} user={user} />;
      case "AI Providers": return <Providers wa={wa} user={user} />;
      case "Activity": return <Activity wa={wa} user={user} />;
      case "Settings": return <Settings onSignOut={signOut} />;
    }
  };

  return (
    <main className="shell">
      <nav className="rail" aria-label="Main">
        <div className="wordmark">Medot<span className="dot">.</span></div>
        {PAGES.map((p) => (
          <button key={p} type="button" className="tab" aria-current={page === p ? "page" : undefined}
             onClick={() => setPage(p)}>
            {p}
          </button>
        ))}
        <div className="rail-footer">Window close keeps Me. running — quit from the tray.</div>
      </nav>
      <div className="page">
        <div className="page-inner">{renderPage()}</div>
      </div>
    </main>
  );
}
