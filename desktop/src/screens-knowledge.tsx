import { useCallback, useEffect, useState } from "react";
import { api, type WaStatus } from "./lib/api";

/** Knowledge — what Me. remembers: areas → topics → facts with dates (doc 07). */

type Domain = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  owner_identity_id: string;
  topics: number;
  facts: number;
  latest_fact_at: string | null;
};

type Topic = { id: string; name: string; summary: string; node_type: string };

type Fact = {
  id: string;
  fact: string;
  relation: string;
  valid_from: string;
  valid_to: string | null;
};

type StructuredRecord = {
  id: string;
  type_key: string;
  type_title: string;
  data: Record<string, unknown>;
  occurred_at: string;
};

type DomainDetail = { domain: Domain; topics: Topic[]; facts: Fact[] };
type DomainRecords = { records: StructuredRecord[] };
type DomainData = { detail: DomainDetail; records: StructuredRecord[] };

const fmtDate = (iso: string | null | undefined): string => iso?.slice(0, 10) ?? "";

const areaSub = (d: Domain): string =>
  [d.summary, `${d.topics} topics · ${d.facts} facts`, fmtDate(d.latest_fact_at)]
    .filter(Boolean)
    .join(" · ");

const dataPreview = (data: Record<string, unknown>): string =>
  Object.entries(data)
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(" · ");

function EmptyRow({ text }: { text: string }) {
  return (
    <div className="run-row tentative">
      <span className="what">{text}</span>
    </div>
  );
}

function DomainPanel({ data }: { data: DomainData }) {
  const { detail, records } = data;
  return (
    <>
      <div className="section-label">Topics</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {detail.topics.length === 0 && <EmptyRow text="No topics yet." />}
        {detail.topics.map((t) => (
          <div className="run-row" key={t.id}>
            <span className="what">
              {t.name}
              {t.summary && <span className="entry-sub"> {t.summary}</span>}
            </span>
          </div>
        ))}
      </div>

      <div className="section-label">Facts</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {detail.facts.length === 0 && (
          <EmptyRow text="No facts yet — talk to Me. and it will remember." />
        )}
        {detail.facts.map((f) => {
          const sub = [f.relation, f.valid_to ? "superseded" : ""]
            .filter(Boolean)
            .join(" · ");
          return (
            <div className={`run-row${f.valid_to ? " tentative" : ""}`} key={f.id}>
              <span className="what">
                {f.fact}
                {sub && <span className="entry-sub"> {sub}</span>}
              </span>
              <span className="when">{fmtDate(f.valid_from)}</span>
            </div>
          );
        })}
      </div>

      <div className="section-label">Records</div>
      <div className="entries" style={{ marginTop: 6 }}>
        {records.length === 0 && (
          <EmptyRow text="No structured records yet — tell Me. something concrete, like “log my weight 74.2”." />
        )}
        {records.map((r) => {
          const pv = dataPreview(r.data);
          return (
            <div className="run-row" key={r.id}>
              <span className="what">
                {r.type_title}
                {pv && <span className="entry-sub"> {pv}</span>}
              </span>
              <span className="when">{fmtDate(r.occurred_at)}</span>
            </div>
          );
        })}
      </div>
    </>
  );
}

export function Knowledge(_: { wa: WaStatus | null; user: unknown }) {
  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, DomainData>>({});
  const [expandErrorId, setExpandErrorId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const v = await api<{ domains: Domain[]; episodes_total: number }>("/knowledge");
      setDomains(v.domains);
    } catch {
      setDomains(null);
      setLoadError(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const open = async (id: string) => {
    setOpenId(id);
    if (cache[id]) return;
    setExpandErrorId(null);
    try {
      const [detail, recs] = await Promise.all([
        api<DomainDetail>(`/knowledge/domains/${id}`),
        api<DomainRecords>(`/knowledge/domains/${id}/records`),
      ]);
      setCache((c) => ({ ...c, [id]: { detail, records: recs.records } }));
    } catch {
      setExpandErrorId(id);
    }
  };

  const toggle = (id: string) => {
    if (openId === id) setOpenId(null);
    else void open(id);
  };

  const areas = (domains ?? [])
    .slice()
    .sort((a, b) => {
      if (a.slug === "global") return -1;
      if (b.slug === "global") return 1;
      return a.title.localeCompare(b.title);
    });

  return (
    <>
      <div className="page-heading">
        <h1>Knowledge</h1>
        <p className="subline">
          What Me. remembers, organized into areas. Everything here was said to
          Me. first.
        </p>
      </div>
      {loadError && (
        <div className="entries">
          <section className="entry">
            <div className="entry-sub" role="alert">
              Couldn't load your knowledge areas — is the Medot daemon running?{" "}
              <button className="link" type="button" onClick={() => { void load(); }}>
                Try again
              </button>
            </div>
          </section>
        </div>
      )}
      <div className="entries">
        {areas.map((d) => (
          <section className="entry" key={d.id}>
            <div className="entry-title">
              <span className="status-dot" aria-hidden="true" />{" "}
              <button className="link" type="button" onClick={() => toggle(d.id)}>
                {d.title}
              </button>
            </div>
            <div className="entry-sub">{areaSub(d)}</div>
            {openId === d.id && (
              <div style={{ marginTop: 8 }}>
                {expandErrorId === d.id ? (
                  <div className="entry-sub" role="alert">
                    Couldn't open {d.title}.{" "}
                    <button className="link" type="button" onClick={() => void open(d.id)}>
                      Try again
                    </button>
                  </div>
                ) : cache[d.id] ? (
                  <DomainPanel data={cache[d.id]} />
                ) : (
                  <EmptyRow text="Opening…" />
                )}
              </div>
            )}
          </section>
        ))}
      </div>
    </>
  );
}
