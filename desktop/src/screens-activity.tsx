import { useCallback, useEffect, useState } from "react";
import { api, type ActivityEvent, type Approval, type WaStatus } from "./lib/api";

/** Activity — what Me. asked permission for, and what it did. */

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.replace("T", " · ").replace("Z", "");
}

const subStyle = { margin: "4px 12px" };

export function Activity(_: { wa: WaStatus | null; user: unknown }) {
  const [pending, setPending] = useState<Approval[] | null>(null);
  const [recent, setRecent] = useState<Approval[]>([]);
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [decideErrors, setDecideErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const [ap, ev] = await Promise.all([
        api<{ pending: Approval[]; recent: Approval[] }>("/approvals"),
        api<{ events: ActivityEvent[] }>("/activity"),
      ]);
      setPending(ap.pending);
      setRecent(ap.recent);
      setEvents(ev.events);
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = async (a: Approval, approved: boolean) => {
    setBusyId(a.id);
    setDecideErrors((e) => ({ ...e, [a.id]: "" }));
    try {
      const r = await api<{ reply?: string | null }>(`/approvals/${a.id}/decide`, {
        method: "POST",
        body: JSON.stringify({ approved }),
      });
      const reply = r.reply;
      if (reply) setReplies((v) => ({ ...v, [a.id]: reply }));
      await load();
    } catch (err) {
      setDecideErrors((e) => ({ ...e, [a.id]: String(err) }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <div className="page-heading">
        <h1>Activity</h1>
        <p className="subline">What Me. did, and what it asked permission for.</p>
      </div>
      {loadError && (
        <div className="entries">
          <section className="entry">
            <div className="entry-sub" role="alert">
              Couldn't load approvals and activity — is the Medot daemon running?{" "}
              <button className="link" type="button" onClick={() => { load(); }}>Try again</button>
            </div>
          </section>
        </div>
      )}

      <div className="section-label">What Me. asked permission for</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {pending !== null && pending.length === 0 && (
          <section className="entry">
            <div className="entry-title">Nothing waiting — Me. asks before acting on anything destructive.</div>
          </section>
        )}
        {(pending ?? []).map((a) => (
          <section className="entry" key={a.id}>
            <div className="run-row">
              <span className="what">
                <span className="status-dot off" aria-hidden="true" />
                {" "}{a.action}
              </span>
              <span className="when">
                <button className="btn" type="button" disabled={busyId === a.id} onClick={() => decide(a, true)}>
                  Approve
                </button>{" "}
                <button className="btn-ghost" type="button" disabled={busyId === a.id} onClick={() => decide(a, false)}>
                  Deny
                </button>
              </span>
            </div>
            <div className="entry-sub" style={subStyle}>{a.summary}</div>
            {decideErrors[a.id] && (
              <div role="alert" className="entry-sub" style={subStyle}>
                Couldn't decide: {decideErrors[a.id]}
              </div>
            )}
          </section>
        ))}
        {recent.map((a) => (
          <section className="entry" key={a.id}>
            <div className="run-row">
              <span className="what">{a.action}</span>
              <span className="when">{a.status} · {fmtWhen(a.decided_at)}</span>
            </div>
            <div className="entry-sub" style={subStyle}>{a.summary}</div>
            {replies[a.id] && (
              <div className="entry-sub" style={subStyle}>Me.: {replies[a.id]}</div>
            )}
          </section>
        ))}
      </div>

      <div className="section-label">What Me. did</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {events !== null && events.length === 0 && (
          <section className="entry">
            <div className="entry-sub">Nothing yet — Me. hasn't acted on anything.</div>
          </section>
        )}
        {(events ?? []).map((ev) => {
          const detail = ev.detail ?? {};
          const preview = Object.keys(detail).length
            ? JSON.stringify(detail).slice(0, 120)
            : "";
          return (
            <section className="entry" key={ev.id}>
              <div className="run-row">
                <span className="what">{ev.event}</span>
                <span className="when">{fmtWhen(ev.created_at)}</span>
              </div>
              {preview && <div className="entry-sub" style={subStyle}>{preview}</div>}
            </section>
          );
        })}
      </div>
    </>
  );
}
