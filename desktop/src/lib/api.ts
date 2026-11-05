/** Runtime API client — loopback HTTP with the per-launch token. */

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
    window.dispatchEvent(new CustomEvent("medot:session-changed"));
  } catch (err) {
    console.error("deep-link sign-in failed", err);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
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
  return (await res.json()) as T;
}

// ---- shared response types -------------------------------------------------

export type WaRoute = {
  transport: string;
  connected?: boolean;
  running?: boolean;
  error?: string | null;
  connected_at?: string | null;
};

export type WaStatus = {
  agent_platform: WaRoute;
  baileys: WaRoute;
  any_connected: boolean;
};

export type Session = { authenticated: boolean; user_id?: string; expires_at?: string | null };

export type Identity = {
  id: string;
  name: string;
  slug: string;
  kind: string;
  status: string;
  description: string;
  icon: string | null;
  model_profile_id: string | null;
  instructions_md: string;
  instructions_version: number | null;
};

export type Approval = {
  id: string;
  action: string;
  summary: string;
  status: string;
  channel: string;
  expires_at: string | null;
  decided_at: string | null;
};

export type ActivityEvent = {
  id: string;
  event: string;
  detail: Record<string, unknown>;
  created_at: string | null;
  identity_id: string | null;
};

export type ModelProfileLite = { id: string; name: string; purpose: string; model: string };
