import { useEffect, useState } from "react";
import { api, type Session, type WaStatus } from "./lib/api";

type ScreenProps = { wa: WaStatus | null; user: Session | null };

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.replace("T", " · ").replace("Z", "");
}

function Greeting() {
  const hour = new Date().getHours();
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  return (
    <div className="page-heading">
      <h1>Overview</h1>
      <p className="subline">Good {part} — here is your companion right now.</p>
    </div>
  );
}

function RouteRow({ label, route, onConnect }: { label: string; route?: { connected?: boolean; connected_at?: string | null; error?: string | null }; onConnect?: () => void }) {
  if (route?.connected) {
    return (
      <div className="run-row">
        <span className="what"><span className="status-dot" aria-hidden="true" />{label} — connected</span>
        <span className="when">{fmtWhen(route.connected_at)}</span>
      </div>
    );
  }
  if (route?.error) {
    console.error(`${label}:`, route.error);
  }
  return (
    <div className="run-row tentative">
      <span className="what">
        <span className="status-dot off" aria-hidden="true" />
        {label} — not connected{route?.error ? " · connection error — try connecting again" : ""}
      </span>
      <span className="when">{onConnect && <button className="link" type="button" onClick={onConnect}>Connect</button>}</span>
    </div>
  );
}

export function Overview({ wa, onConnect, go }: { wa: WaStatus | null; onConnect: () => void; go: (p: "AI Providers") => void }) {
  return (
    <>
      <Greeting />
      <div className="entries">
        <section className="entry" aria-label="Me.">
          <div className="entry-title">Me. — your companion</div>
          <div className="entry-sub">{wa?.any_connected ? "Active, listening on WhatsApp." : "Waiting to be connected — connect a WhatsApp route below."} Coordinator of your spaces.</div>
        </section>

        <section className="entry" aria-label="WhatsApp connection">
          <div className="entry-title">WhatsApp</div>
          <div className="entry-rows">
            <RouteRow label="Official route (Agent Platform)" route={wa?.agent_platform} onConnect={onConnect} />
            <RouteRow label="QR route (Baileys)" route={wa?.baileys} onConnect={onConnect} />
          </div>
        </section>

        <section className="entry" aria-label="AI model">
          <div className="entry-title">AI model</div>
          <div className="run-row">
            <span className="what">Not set up yet. Pick a provider so Me. can think.</span>
            <span className="when"><button className="link" type="button" onClick={() => go("AI Providers")}>Set up</button></span>
          </div>
        </section>
      </div>

      <div className="section-label">Recent activity</div>
      <div className="entries" style={{ marginTop: 6 }}>
        <section className="entry" aria-label="Recent activity">
          <div className="entry-rows">
            {wa?.agent_platform.connected && (
              <div className="run-row">
                <span className="what">Connected WhatsApp through the official Agent Platform</span>
                <span className="when">{fmtWhen(wa.agent_platform.connected_at)}</span>
              </div>
            )}
            {wa?.baileys.connected && (
              <div className="run-row">
                <span className="what">Paired WhatsApp through the Baileys bridge</span>
                <span className="when">{fmtWhen(wa.baileys.connected_at)}</span>
              </div>
            )}
            <div className="run-row tentative">
              <span className="what">Full activity timeline arrives with the runtime engine</span>
              <span className="when">soon</span>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

export function Identities({ wa }: ScreenProps) {
  return (
    <>
      <div className="page-heading">
        <h1>Identities</h1>
        <p className="subline">
          Me. is your permanent companion; specialists are its delegations.
        </p>
      </div>
      <div className="entries">
        <section className="entry">
          <div className="entry-title"><span className="status-dot" aria-hidden="true" />Me. — your companion</div>
          <div className="entry-sub">Coordinator of your spaces. Never replaced — it delegates.</div>
          <div className="status-lines">
            <span>Active{wa?.any_connected ? " and listening on WhatsApp" : ""}.</span>
          </div>
        </section>
      </div>
      <div className="section-label">Specialist spaces</div>
      <div className="entries" style={{ marginTop: 6 }}>
        <section className="entry">
          <div className="entry-title">No specialist spaces yet</div>
          <div className="entry-sub">
            When an area of your life grows — health, studies, a business —
            Me. will suggest starting a space for it. You always confirm first.
          </div>
        </section>
      </div>
    </>
  );
}

function ComingSoon({ title, milestone, note }: { title: string; milestone: string; note: string }) {
  return (
    <>
      <div className="page-heading">
        <h1>{title}</h1>
        <p className="subline">{note}</p>
      </div>
      <div className="entries">
        <section className="entry">
          <div className="entry-title">Arrives with {milestone}</div>
          <div className="entry-sub">
            Me. is already listening on WhatsApp, and what you share is being
            remembered already.
          </div>
        </section>
      </div>
    </>
  );
}

export function Knowledge(_: ScreenProps) {
  return (
    <ComingSoon
      title="Knowledge"
      milestone="milestone 3"
      note="Your life as a private knowledge space — areas, topics, facts with dates."
    />
  );
}

export function Connectors(_: ScreenProps) {
  return (
    <ComingSoon
      title="Connectors"
      milestone="milestone 7"
      note="Email, calendar and task accounts — connected accounts Me. may use, per identity."
    />
  );
}

export function Providers(_: ScreenProps) {
  return (
    <ComingSoon
      title="AI Providers"
      milestone="milestone 2"
      note="Pick a provider (local Ollama or a cloud model); the key goes to your OS keystore — never into files."
    />
  );
}

export function Activity({ wa }: ScreenProps) {
  return (
    <>
      <div className="page-heading">
        <h1>Activity</h1>
        <p className="subline">What Me. did, and what it asked permission for.</p>
      </div>
      <div className="entries">
        <section className="entry">
          <div className="entry-rows">
            {wa?.agent_platform.connected && (
              <div className="run-row">
                <span className="what">Connected WhatsApp through the official Agent Platform</span>
                <span className="when">{fmtWhen(wa.agent_platform.connected_at)}</span>
              </div>
            )}
            {wa?.baileys.connected && (
              <div className="run-row">
                <span className="what">Paired WhatsApp through the Baileys bridge</span>
                <span className="when">{fmtWhen(wa.baileys.connected_at)}</span>
              </div>
            )}
            <div className="run-row tentative">
              <span className="what">Runs, approvals and fact changes arrive with the runtime engine</span>
              <span className="when">soon</span>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

type SettingsProps = { onSignOut: () => void };

export function Settings({ onSignOut }: SettingsProps) {
  const [paths, setPaths] = useState<Record<string, string> | null>(null);
  const [pathsError, setPathsError] = useState(false);
  const loadPaths = () => {
    setPathsError(false);
    const controller = new AbortController();
    const giveUp = setTimeout(() => controller.abort(), 10_000);
    api<Record<string, string>>("/paths", { signal: controller.signal })
      .then((v) => {
        clearTimeout(giveUp);
        setPaths(v);
      })
      .catch(() => {
        clearTimeout(giveUp);
        setPaths(null);
        setPathsError(true);
      });
  };
  useEffect(loadPaths, []);
  return (
    <>
      <div className="page-heading">
        <h1>Settings</h1>
        <p className="subline">Your account, your files, your control.</p>
      </div>
      <div className="entries">
        <section className="entry">
          <div className="entry-title">Account</div>
          <div className="entry-sub">Signed in with Google.</div>
          <div className="run-row" style={{ borderBottom: "none" }}>
            <span className="what">Use Medot on this computer only</span>
            <span className="when">
              <button className="link" type="button" onClick={onSignOut}>Sign out</button>
            </span>
          </div>
        </section>
        <section className="entry">
          <div className="entry-title">Where your files live</div>
          <div className="status-lines">
            {paths
              ? Object.entries(paths).map(([name, p]) => (
                  <span key={name} className="entry-sub"><code>{name}</code> — <code>{p}</code></span>
                ))
              : pathsError
                ? <span className="entry-sub">Couldn't read your folder settings. <button className="link" type="button" onClick={loadPaths}>Try again</button></span>
                : <span className="entry-sub">Opening the workspace…</span>}
          </div>
        </section>
        <section className="entry">
          <div className="entry-title">Closing the window</div>
          <div className="entry-sub">
            Closing this window keeps Me. running so it can hear WhatsApp.
            Quit Medot fully from the tray icon.
          </div>
        </section>
      </div>
    </>
  );
}
