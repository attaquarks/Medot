import { useCallback, useEffect, useState } from "react";
import { api } from "./lib/api";

type Profile = {
  id: string;
  name: string;
  purpose: string;
  provider: string;
  model: string;
  api_base: string | null;
};

const PROVIDER_KINDS = [
  { value: "openai_compatible", label: "OpenAI-compatible (OpenAI, Groq, OpenRouter, LM Studio…)" },
  { value: "ollama", label: "Ollama (local)" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "google", label: "Google (Gemini)" },
];

const selectStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  font: "inherit",
  border: "1px solid var(--border-strong)",
  borderRadius: 8,
  background: "var(--surface)",
};

/** AI Providers — BYOK: any provider, any model; keys go to the OS keystore. */
export function Providers(_: { wa: unknown; user: unknown }) {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [provider, setProvider] = useState("openai_compatible");
  const [apiBase, setApiBase] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("chat");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [verifyResult, setVerifyResult] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const r = await api<{ profiles: Profile[] }>("/providers/profiles");
    setProfiles(r.profiles);
  }, []);
  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, [load]);

  const clean = (e: unknown) => String(e).replace(/^Error: \d+: /, "");

  const fetchModels = useCallback(async () => {
    setError("");
    setBusy("Fetching models…");
    try {
      const r = await api<{ models: string[] }>("/providers/discover", {
        method: "POST",
        body: JSON.stringify({ provider, api_base: apiBase || null, api_key: apiKey }),
      });
      setModels(r.models);
      if (!r.models.length) setError("The key works but the provider returned no models.");
    } catch (e) {
      setError(clean(e));
    } finally {
      setBusy("");
    }
  }, [provider, apiBase, apiKey]);

  const save = useCallback(async () => {
    setError("");
    setBusy("Saving…");
    try {
      await api("/providers/profiles", {
        method: "POST",
        body: JSON.stringify({
          name,
          purpose,
          provider,
          model,
          api_base: apiBase || null,
          api_key: apiKey || null,
        }),
      });
      setName("");
      setApiKey("");
      setModels([]);
      setModel("");
      await load();
    } catch (e) {
      setError(clean(e));
    } finally {
      setBusy("");
    }
  }, [name, purpose, provider, model, apiBase, apiKey, load]);

  const verify = useCallback(async (id: string) => {
    setError("");
    setVerifyResult((v) => ({ ...v, [id]: "Calling the model…" }));
    try {
      const r = await api<{ ok: boolean; latency_ms: number; sample: string }>(
        `/providers/profiles/${id}/verify`,
        { method: "POST" },
      );
      setVerifyResult((v) => ({ ...v, [id]: `Working — ${r.latency_ms} ms — replied: ${r.sample}` }));
    } catch (e) {
      setVerifyResult((v) => ({ ...v, [id]: `Failed: ${clean(e)}` }));
    }
  }, []);

  const remove = useCallback(
    async (id: string) => {
      await api(`/providers/profiles/${id}`, { method: "DELETE" });
      await load();
    },
    [load],
  );

  return (
    <>
      <div className="page-heading">
        <h1>AI Providers</h1>
        <p className="subline">
          Bring your own key — any provider, any model. Keys go to your
          computer's secure storage, never into files or the cloud.
        </p>
      </div>

      <div className="entries">
        <section className="entry">
          <div className="entry-title">Add a model profile</div>
          <label className="field-label" htmlFor="p-kind">Provider</label>
          <select id="p-kind" value={provider} onChange={(e) => setProvider(e.target.value)} style={selectStyle}>
            {PROVIDER_KINDS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
          {(provider === "openai_compatible" || provider === "ollama") && (
            <>
              <label className="field-label" htmlFor="p-base">
                Server URL{provider === "ollama" ? " (default: http://127.0.0.1:11434)" : ""}
              </label>
              <input
                id="p-base"
                type="text"
                placeholder={provider === "ollama" ? "http://127.0.0.1:11434" : "https://api.openai.com/v1"}
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
              />
            </>
          )}
          {provider !== "ollama" && (
            <>
              <label className="field-label" htmlFor="p-key">API key</label>
              <input
                id="p-key"
                type="password"
                placeholder="Paste your key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </>
          )}
          <p style={{ marginTop: 12 }}>
            <button
              className="btn"
              type="button"
              onClick={fetchModels}
              disabled={!!busy || (provider !== "ollama" && !apiKey)}
            >
              Fetch models
            </button>
          </p>
          {models.length > 0 && (
            <>
              <label className="field-label" htmlFor="p-model">Model ({models.length} found)</label>
              <select
                id="p-model"
                value={models.includes(model) ? model : ""}
                onChange={(e) => setModel(e.target.value)}
                style={selectStyle}
              >
                <option value="" disabled>Pick a model…</option>
                {models.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <p className="entry-sub" style={{ marginTop: 6 }}>
                or type an id:{" "}
                <input type="text" style={{ width: "50%" }} value={model} onChange={(e) => setModel(e.target.value)} />
              </p>
            </>
          )}
          {model && (
            <>
              <label className="field-label" htmlFor="p-name">Profile name</label>
              <input
                id="p-name"
                type="text"
                placeholder="e.g. My main model"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <label className="field-label" htmlFor="p-purpose">Used for</label>
              <select id="p-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} style={selectStyle}>
                <option value="chat">Chat (Me. talks with this)</option>
                <option value="extraction">Memory extraction (reading facts)</option>
                <option value="planning">Planning</option>
                <option value="embedding">Embeddings (search)</option>
              </select>
              <p style={{ marginTop: 14 }}>
                <button className="btn" type="button" onClick={save} disabled={!!busy || !name}>
                  Save profile
                </button>
              </p>
            </>
          )}
          {busy && <p className="ok-note">{busy}</p>}
          {error && <p role="alert" className="error">{error}</p>}
        </section>
      </div>

      <div className="section-label">Your model profiles</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {(profiles ?? []).map((pr) => (
          <section className="entry" key={pr.id}>
            <div className="entry-title">{pr.name}</div>
            <div className="entry-sub">
              {pr.provider} · {pr.model} · used for {pr.purpose}
            </div>
            <div className="run-row" style={{ borderBottom: "none" }}>
              <span className="what">{verifyResult[pr.id] ?? ""}</span>
              <span className="when">
                <button className="link" type="button" onClick={() => verify(pr.id)}>Test</button>
                {" "}
                <button className="link" type="button" onClick={() => remove(pr.id)}>Delete</button>
              </span>
            </div>
          </section>
        ))}
        {profiles && !profiles.length && (
          <section className="entry">
            <div className="entry-title">No model profiles yet</div>
            <div className="entry-sub">Add one above — Me. needs a model to think with.</div>
          </section>
        )}
      </div>
    </>
  );
}
