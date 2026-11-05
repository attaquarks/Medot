import { useCallback, useEffect, useState } from "react";
import { api, type WaStatus, type Identity, type ModelProfileLite } from "./lib/api";

/** Identities — Me. plus the specialists it coordinates (M2b/M2c console). */

const fieldStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  font: "inherit"
};

function IdentityRow({ identity, profiles, onChanged }: {
  identity: Identity;
  profiles: ModelProfileLite[];
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const active = identity.status === "active";
  const profileName = (id: string | null) => profiles.find((p) => p.id === id)?.name;

  const toggle = async () => {
    await api(`/identities/${identity.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: active ? "deactivated" : "active" }),
    });
    onChanged();
  };

  return (
    <section className="entry">
      <div className="run-row" style={{ borderBottom: "none" }}>
        <span className="what">
          <span className={`status-dot${active ? "" : " off"}`} aria-hidden="true" />
          {" "}{identity.name}{" "}
          <span className="entry-sub">/{identity.slug} · {profileName(identity.model_profile_id) ?? "default model"}</span>
        </span>
        <span className="when">
          <button className="link" type="button" onClick={() => setOpen(!open)}>{open ? "Close" : "Edit"}</button>
          {" · "}
          <button className="link" type="button" onClick={toggle}>{active ? "Deactivate" : "Activate"}</button>
        </span>
      </div>
      {identity.description && (
        <div className="entry-sub" style={{ margin: "4px 12px" }}>{identity.description}</div>
      )}
    </section>
  );
}


function InstructionsEditor({ identity, onDone }: { identity: Identity; onDone: () => void }) {
  const [draft, setDraft] = useState(identity.instructions_md);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await api(`/identities/${identity.id}/instructions`, {
        method: "PUT",
        body: JSON.stringify({ content_md: draft }),
      });
      onDone();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="entry-rows">
      <textarea
        aria-label={`Instructions for ${identity.name}`}
        rows={6}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        style={{ ...fieldStyle, resize: "vertical" }}
      />
      {error && <span role="alert" className="entry-sub">Couldn't save: {error}</span>}
      <div className="run-row" style={{ borderBottom: "none" }}>
        <span className="what entry-sub">Version {identity.instructions_version ?? 1} — saving starts a new version.</span>
        <span className="when">
          <button className="btn" type="button" onClick={save} disabled={busy || !draft.trim()}>Save</button>
        </span>
      </div>
    </div>
  );
}

export function Identities(_: { wa: WaStatus | null; user: unknown }) {
  const [identities, setIdentities] = useState<Identity[] | null>(null);
  const [profiles, setProfiles] = useState<ModelProfileLite[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [modelProfileId, setModelProfileId] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [editingMe, setEditingMe] = useState(false);

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const [ids, profs] = await Promise.all([
        api<{ identities: Identity[] }>("/identities"),
        api<{ profiles: ModelProfileLite[] }>("/providers/profiles"),
      ]);
      setIdentities(ids.identities);
      setProfiles(profs.profiles.filter((p) => p.purpose === "chat"));
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setBusy(true);
    setFormError("");
    try {
      await api("/identities", {
        method: "POST",
        body: JSON.stringify({
          name,
          description,
          instructions_md: instructions,
          model_profile_id: modelProfileId || null,
        }),
      });
      setShowForm(false);
      setName("");
      setDescription("");
      setInstructions("");
      setModelProfileId("");
      await load();
    } catch (err) {
      setFormError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const me = identities?.find((i) => i.kind === "coordinator");
  const specialists = identities?.filter((i) => i.kind !== "coordinator") ?? [];

  return (
    <>
      <div className="page-heading">
        <h1>Identities</h1>
        <p className="subline">
          Me. is your permanent companion; specialists are its delegations.
        </p>
      </div>
      {loadError && (
        <div className="entries">
          <section className="entry">
            <div className="entry-sub" role="alert">
              Couldn't load identities — is the Medot daemon running?
            </div>
          </section>
        </div>
      )}
      <div className="entries">
        {me && (
          <section className="entry">
            <div className="run-row" style={{ borderBottom: "none" }}>
              <span className="what">
                <span className="status-dot" aria-hidden="true" />
                {" "}Me. — your companion
              </span>
              <span className="when">
                <button className="link" type="button" onClick={() => setEditingMe(!editingMe)}>Edit</button>
              </span>
            </div>
            <div className="entry-sub">Coordinator of your spaces. Never replaced — it delegates.</div>
          </section>
        )}
      </div>
      {editingMe && me && (
        <section className="entry">
          <InstructionsEditor
            identity={me}
            onDone={() => {
              setEditingMe(false);
              load();
            }}
          />
        </section>
      )}
      <div className="section-label">Specialist spaces</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {specialists.length === 0 && (
          <section className="entry">
            <div className="entry-title">No specialist spaces yet</div>
            <div className="entry-sub">
              When an area of your life grows — health, studies, a business —
              Me. will suggest starting a space for it. You always confirm first.
            </div>
          </section>
        )}
        {specialists.map((sp) => (
          <IdentityRow key={sp.id} identity={sp} profiles={profiles} onChanged={load} />
        ))}
      </div>
      <div className="section-label">Start a space</div>
      {showForm ? (
        <div className="entries" style={{ marginTop: 6 }}>
          <section className="entry">
            <label className="field-label" htmlFor="sp-name">Name</label>
            <input
              id="sp-name"
              type="text"
              placeholder="e.g. Health, Studies, Business"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={fieldStyle}
            />
            <label className="field-label" htmlFor="sp-description">Description (optional)</label>
            <input
              id="sp-description"
              type="text"
              placeholder="What is this space about?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={fieldStyle}
            />
            <label className="field-label" htmlFor="sp-instructions">Instructions</label>
            <textarea
              id="sp-instructions"
              rows={4}
              placeholder="How should this specialist think and behave?"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              style={{ ...fieldStyle, resize: "vertical" }}
            />
            <label className="field-label" htmlFor="sp-model">Model</label>
            <select
              id="sp-model"
              value={modelProfileId}
              onChange={(e) => setModelProfileId(e.target.value)}
              style={fieldStyle}
            >
              <option value="">Default model</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.model})</option>
              ))}
            </select>
            {formError && <span role="alert" className="entry-sub">{formError}</span>}
            <p style={{ marginTop: 12 }}>
              <button
                className="btn"
                type="button"
                onClick={create}
                disabled={busy || !name.trim() || !instructions.trim()}
              >
                Start space
              </button>
            </p>
          </section>
        </div>
      ) : (
        <p style={{ marginTop: 6 }}>
          <button className="btn-ghost" type="button" onClick={() => setShowForm(true)}>
            Start a space…
          </button>
        </p>
      )}
    </>
  );
}
