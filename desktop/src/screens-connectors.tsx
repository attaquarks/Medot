import { useCallback, useEffect, useState } from "react";
import { api, type WaStatus } from "./lib/api";

/** Connectors — MCP servers Me. can use: one-click directory plus any URL. */

type Connector = {
  id: string;
  provider: string;
  account_label: string;
  url: string;
  auth_header_name: string | null;
  enabled: boolean;
  status: string;
  connected_at: string | null;
};

type CatalogEntry = {
  key: string;
  title: string;
  blurb: string;
  url: string;
  auth_header_name: string | null;
  auth_hint: string;
};

type TestResult = { ok: boolean; tools: string[]; error?: string };

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "10px 12px", font: "inherit",
  border: "1px solid var(--border-strong)", borderRadius: 8, background: "var(--surface)",
};

const hostOf = (url: string): string => {
  try { return new URL(url).host; } catch { return url; }
};

const clean = (e: unknown) => String(e).replace(/^Error: \d+: /, "");

export function Connectors(_: { wa: WaStatus | null; user: unknown }) {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [tests, setTests] = useState<Record<string, TestResult>>({});
  const [actionError, setActionError] = useState("");
  const [dirError, setDirError] = useState("");
  const [tokenFor, setTokenFor] = useState<string | null>(null);
  const [tokenHint, setTokenHint] = useState("");
  const [tokenValue, setTokenValue] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ provider: "custom", name: "", url: "", header: "", value: "", hint: "" });
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const [conn, cat] = await Promise.all([
        api<{ connectors: Connector[] }>("/connectors"),
        api<{ catalog: CatalogEntry[] }>("/connectors/catalog"),
      ]);
      setConnectors(conn.connectors);
      setCatalog(cat.catalog);
    } catch {
      setConnectors(null);
      setLoadError(true);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const openForm = (pre?: CatalogEntry) => {
    setFormOpen(true);
    setFormError("");
    setForm({
      provider: pre?.key ?? "custom", name: pre?.title ?? "", url: "",
      header: pre?.auth_header_name ?? "", value: "", hint: pre?.auth_hint ?? "",
    });
  };

  const addFromDirectory = async (entry: CatalogEntry) => {
    if (!entry.url) { openForm(entry); return; }
    setDirError("");
    setBusyId(entry.key);
    try {
      const row = await api<Connector>("/connectors", {
        method: "POST",
        body: JSON.stringify({
          provider: entry.key, account_label: entry.title, url: entry.url,
          auth_header_name: entry.auth_header_name || null,
        }),
      });
      await load();
      if (entry.auth_hint) { setTokenFor(row.id); setTokenHint(entry.auth_hint); setTokenValue(""); }
    } catch (e) { setDirError(clean(e)); } finally { setBusyId(""); }
  };

  const submitForm = async () => {
    setBusyId("form");
    try {
      await api<Connector>("/connectors", {
        method: "POST",
        body: JSON.stringify({
          provider: form.provider || "custom", account_label: form.name.trim() || "Custom connector",
          url: form.url, auth_header_name: form.header.trim() || null, auth_header_value: form.value || null,
        }),
      });
      setFormOpen(false);
      setForm((f) => ({ ...f, url: "", value: "" }));
      await load();
    } catch (e) { setFormError(clean(e)); } finally { setBusyId(""); }
  };

  const patch = async (c: Connector, body: Record<string, unknown>): Promise<boolean> => {
    setActionError("");
    setBusyId(c.id);
    try {
      await api(`/connectors/${c.id}`, { method: "PATCH", body: JSON.stringify(body) });
      await load();
      return true;
    } catch (e) { setActionError(clean(e)); return false; } finally { setBusyId(""); }
  };

  const remove = async (c: Connector) => {
    setActionError("");
    setBusyId(c.id);
    try {
      await api(`/connectors/${c.id}`, { method: "DELETE" });
      setTests((t) => { const n = { ...t }; delete n[c.id]; return n; });
      if (tokenFor === c.id) setTokenFor(null);
      await load();
    } catch (e) { setActionError(clean(e)); } finally { setBusyId(""); }
  };

  const test = async (c: Connector) => {
    setActionError("");
    setBusyId(c.id);
    try {
      const r = await api<TestResult>(`/connectors/${c.id}/test`, { method: "POST" });
      setTests((t) => ({ ...t, [c.id]: r }));
    } catch (e) {
      setTests((t) => ({ ...t, [c.id]: { ok: false, tools: [], error: clean(e) } }));
    } finally { setBusyId(""); }
  };

  const saveToken = async (c: Connector) => {
    if (await patch(c, { auth_header_value: tokenValue })) { setTokenFor(null); setTokenValue(""); }
  };

  const rows = connectors ?? [];
  const directory = catalog.filter((e) => e.key !== "custom");

  return (
    <>
      <div className="page-heading">
        <h1>Connectors</h1>
        <p className="subline">
          Give Me. more abilities — one click for the popular ones, or paste any
          MCP server's URL. Claude-style: tools appear in Me.'s hands right away.
        </p>
      </div>

      <div className="section-label">Your connectors</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {loadError && (
          <section className="entry">
            <div className="entry-sub" role="alert">
              Couldn't load your connectors — is the Medot daemon running?{" "}
              <button className="link" type="button" onClick={() => void load()}>Try again</button>
            </div>
          </section>
        )}
        {actionError && <section className="entry"><div className="entry-sub" role="alert">{actionError}</div></section>}
        {rows.map((c) => {
          const tr = tests[c.id];
          const busy = busyId === c.id;
          return (
            <section className="entry" key={c.id}>
              <div className="run-row">
                <span className="what">
                  <span className={c.enabled ? "status-dot" : "status-dot off"} aria-hidden="true" />
                  {c.account_label}
                  <span className="entry-sub"> {c.provider}</span>
                  <span className="entry-sub"> · {hostOf(c.url)}</span>
                </span>
                <span className="when">
                  <button className="link" type="button" disabled={busy} onClick={() => void test(c)}>Test</button>
                  {" "}
                  <button className="link" type="button" disabled={busy} onClick={() => void patch(c, { enabled: !c.enabled })}>
                    {c.enabled ? "Disable" : "Enable"}
                  </button>
                  {" "}
                  <button className="link" type="button" disabled={busy} onClick={() => void remove(c)}>Remove</button>
                </span>
              </div>
              {tr && (
                <div className="run-row">
                  <span className="what entry-sub">
                    {tr.ok
                      ? `Live — ${tr.tools.length} tools${tr.tools.length ? `: ${tr.tools.slice(0, 5).join(", ")}` : ""}`
                      : <span role="alert">Couldn't reach it: {tr.error}</span>}
                  </span>
                </div>
              )}
              {c.auth_header_name && tokenFor === c.id && (
                <>
                  <label className="field-label" htmlFor={`tok-${c.id}`}>Paste {tokenHint || c.auth_header_name}</label>
                  <input id={`tok-${c.id}`} type="password" style={inputStyle} value={tokenValue}
                    onChange={(e) => setTokenValue(e.target.value)} />
                  <p style={{ marginTop: 10 }}>
                    <button className="link" type="button" disabled={busy} onClick={() => void saveToken(c)}>Save</button>
                  </p>
                </>
              )}
              {c.auth_header_name && tokenFor !== c.id && (
                <div className="run-row" style={{ borderBottom: "none" }}>
                  <span className="what entry-sub">Calls need the {c.auth_header_name} header.</span>
                  <span className="when">
                    <button className="link" type="button" disabled={busy}
                      onClick={() => { setTokenFor(c.id); setTokenHint(""); setTokenValue(""); }}>Set token</button>
                  </span>
                </div>
              )}
            </section>
          );
        })}
        {!loadError && rows.length === 0 && (
          <section className="entry">
            <div className="entry-title">No connectors yet</div>
            <div className="entry-sub">Add one below — Me. picks up its tools right away.</div>
          </section>
        )}
      </div>

      <div className="section-label">Add from the directory</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 6 }}>
        {directory.map((entry) => (
          <section className="entry" key={entry.key}>
            <div className="entry-title">{entry.title}</div>
            <div className="entry-sub">{entry.blurb}</div>
            <p style={{ marginTop: 12, marginBottom: 0 }}>
              <button className="btn-ghost" type="button" disabled={busyId === entry.key}
                onClick={() => void addFromDirectory(entry)}>Add</button>
            </p>
          </section>
        ))}
      </div>
      {dirError && <p className="entry-sub" role="alert" style={{ marginTop: 10 }}>{dirError}</p>}
      <p style={{ marginTop: 14 }}>
        <button className="link" type="button" onClick={() => (formOpen ? setFormOpen(false) : openForm())}>
          {formOpen ? "Hide the form" : "Add a custom connector…"}
        </button>
      </p>

      {formOpen && (
        <section className="entry" style={{ marginTop: 10 }}>
          <div className="entry-title">{form.name ? `Add ${form.name}` : "Add a custom connector"}</div>
          {form.hint && <div className="entry-sub">{form.hint}</div>}
          <label className="field-label" htmlFor="c-url">URL</label>
          <input id="c-url" type="text" style={inputStyle} placeholder="https://…/mcp" value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })} />
          <label className="field-label" htmlFor="c-name">Name</label>
          <input id="c-name" type="text" style={inputStyle} placeholder="Custom connector" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <label className="field-label" htmlFor="c-header">Auth header name (optional)</label>
          <input id="c-header" type="text" style={inputStyle} placeholder="e.g. Authorization" value={form.header}
            onChange={(e) => setForm({ ...form, header: e.target.value })} />
          <label className="field-label" htmlFor="c-value">Auth header value (optional)</label>
          <input id="c-value" type="password" style={inputStyle} placeholder="Paste the token" value={form.value}
            onChange={(e) => setForm({ ...form, value: e.target.value })} />
          <p style={{ marginTop: 14 }}>
            <button className="btn" type="button" disabled={!form.url.trim() || busyId === "form"}
              onClick={() => void submitForm()}>Add connector</button>
          </p>
          {formError && <div className="entry-sub" role="alert">{formError}</div>}
        </section>
      )}
    </>
  );
}
