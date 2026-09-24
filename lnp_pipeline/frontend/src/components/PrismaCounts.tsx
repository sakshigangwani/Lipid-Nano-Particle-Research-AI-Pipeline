import type { PrismaCounts, RunState } from "../types";

interface Props {
  counts: PrismaCounts;
  state: RunState;
  message?: string | null;
}

const DBS: Array<{ key: keyof PrismaCounts; label: string }> = [
  { key: "pubmed", label: "PubMed" },
  { key: "europepmc", label: "Europe PMC" },
  { key: "crossref", label: "CrossRef" },
  { key: "openalex", label: "OpenAlex" },
  { key: "semantic_scholar", label: "Sem. Scholar" },
  { key: "biorxiv", label: "bioRxiv" },
  { key: "arxiv", label: "arXiv" },
];

export default function PrismaCountsPanel({ counts, state, message }: Props) {
  const final = counts.final;
  return (
    <div className="card">
      <div className="progress-header">
        <div className="card-title" style={{ marginBottom: 0 }}>
          Step 2 · Pipeline progress
        </div>
        <div className={`status-badge ${state}`}>
          {state === "running" && <span className="spinner" />}
          {state === "running"
            ? "Running"
            : state === "done"
            ? "Complete"
            : state === "error"
            ? "Error"
            : "Idle"}
        </div>
      </div>

      <div
        style={{
          fontSize: "0.7rem",
          fontWeight: 700,
          letterSpacing: "0.6px",
          textTransform: "uppercase",
          color: "var(--ink-400)",
          marginBottom: 8,
        }}
      >
        Databases searched
      </div>
      <div className="db-hits">
        {DBS.map((db) => {
          const v = counts[db.key] as number;
          return (
            <div
              key={db.key}
              className={`db-hit-card ${v === 0 ? "zero" : ""}`}
            >
              <div className="db-hit-name">{db.label}</div>
              <div className="db-hit-count">{v}</div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          fontSize: "0.7rem",
          fontWeight: 700,
          letterSpacing: "0.6px",
          textTransform: "uppercase",
          color: "var(--ink-400)",
          marginBottom: 8,
        }}
      >
        PRISMA funnel
      </div>
      <div className="funnel">
        <div className="funnel-stage">
          <div className="v">{counts.total_raw}</div>
          <div className="l">raw</div>
        </div>
        <div className="funnel-arrow">→ dedup</div>
        <div className="funnel-stage">
          <div className="v">{counts.after_dedup}</div>
          <div className="l">unique</div>
        </div>
        <div className="funnel-arrow">→ quant</div>
        <div className="funnel-stage">
          <div className="v">{counts.after_quant}</div>
          <div className="l">quant</div>
        </div>
        <div className="funnel-arrow">→ kinetic</div>
        <div className="funnel-stage">
          <div className="v">{counts.after_kinetic}</div>
          <div className="l">kinetic</div>
        </div>
        <div className="funnel-arrow">
          + captions
          <br />({counts.caption_rescued} rescued)
        </div>
        <div className="funnel-stage">
          <div className="v">{counts.llm_scored}</div>
          <div className="l">LLM scored</div>
        </div>
        <div className="funnel-arrow">→ OpenAI</div>
        <div className="funnel-stage final">
          <div className="v">{final}</div>
          <div className="l">included</div>
        </div>
      </div>

      {message && (
        <div
          style={{
            marginTop: 12,
            fontSize: "0.82rem",
            color: "var(--rose-700)",
          }}
        >
          {message}
        </div>
      )}
    </div>
  );
}
