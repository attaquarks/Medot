/** Dev-only preview harness (mock data only) — served at /preview.html.
 *  NOT part of the shipped bundle (vite build only bundles index.html). */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Overview, Identities, Knowledge, Connectors, Providers, Activity, Settings } from "./screens-console";
import { SignIn, ConnectWhatsApp } from "./screens-onboarding";
import type { WaStatus } from "./lib/api";
import "./styles/console.css";

const mockWa: WaStatus = {
  agent_platform: { transport: "agent_platform", connected: true, running: true, error: null, connected_at: "2026-11-02T01:38:00Z" },
  baileys: { transport: "baileys", connected: false, running: false, error: null },
  any_connected: true,
};
const mockWaOff: WaStatus = {
  agent_platform: { transport: "agent_platform", connected: false, running: false, error: null },
  baileys: { transport: "baileys", connected: false, running: false, error: null },
  any_connected: false,
};

function MockRail({ active }: { active: string }) {
  const pages = ["Overview", "Identities", "Knowledge", "Connectors", "AI Providers", "Activity", "Settings"];
  return (
    <nav className="rail" aria-label="Main">
      <div className="wordmark">Medot<span className="dot">.</span></div>
      {pages.map((p) => (
        <span key={p} className="tab" aria-current={p === active ? "page" : undefined}>{p}</span>
      ))}
    </nav>
  );
}

function shell(active: string, inner: React.ReactElement) {
  return (
    <main className="shell">
      <MockRail active={active} />
      <div className="page"><div className="page-inner">{inner}</div></div>
    </main>
  );
}

const routes: Record<string, () => React.ReactElement> = {
  signin: () => <SignIn onSignIn={() => {}} />,
  connect: () => <ConnectWhatsApp onDone={() => {}} />,
  overview: () => shell("Overview", <Overview wa={mockWa} onConnect={() => {}} go={() => {}} />),
  overview_off: () => shell("Overview", <Overview wa={mockWaOff} onConnect={() => {}} go={() => {}} />),
  identities: () => shell("Identities", <Identities wa={mockWa} user={null} />),
  knowledge: () => shell("Knowledge", <Knowledge wa={mockWa} user={null} />),
  connectors: () => shell("Connectors", <Connectors wa={mockWa} user={null} />),
  providers: () => shell("AI Providers", <Providers wa={mockWa} user={null} />),
  activity: () => shell("Activity", <Activity wa={mockWa} user={null} />),
  settings: () => shell("Settings", <Settings onSignOut={() => {}} />),
};

const root = createRoot(document.getElementById("screen-root")!);
root.render(<StrictMode>{(routes[location.hash.replace("#", "")] ?? routes.overview)()}</StrictMode>);
