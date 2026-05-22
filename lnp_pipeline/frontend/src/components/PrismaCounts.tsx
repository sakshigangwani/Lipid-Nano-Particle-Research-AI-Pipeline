import type { PrismaCounts, RunState } from "../types";

interface Props {
  counts: PrismaCounts;
  state: RunState;
  message?: string | null;
}

interface DbCellProps { label: string; value: number; }
function DbCell({ label, value }: DbCellProps) {
  return (
    <div className="prisma-box">
      <div className="db-label">{label}</div>
      <div className="db-count">{value}</div>
    </div>
  );
}

interface ArrowProps { label: string; }
function Arrow({ label }: ArrowProps) {
  return (
    <div className="prisma-arrow">
      <div className="arrow-label">{label}</div>
      <div className="arrow-line" />
      <div className="arrow-head" />
    </div>
  );
}

interface StageProps { count: number; label: string; final?: boolean; }
function Stage({ count, label, final }: StageProps) {
  return (
    <div className={`prisma-stage ${final ? "final" : ""}`}>
      <div className="stage-count">{count}</div>
      <div className="stage-label">{label}</div>
    </div>
  );
}

export default function PrismaCountsPanel({ counts, state, message }: Props) {
  const finalCount = counts.final || counts.after_kinetic;
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Identification · Screening · Eligibility</h2>
        <span className="step-label">PRISMA flow</span>
      </div>

      <div className="prisma-diagram">
        <div className="prisma-tier">
          <DbCell label="PubMed" value={counts.pubmed} />
          <DbCell label="Europe PMC" value={counts.europepmc} />
          <DbCell label="Semantic Scholar" value={counts.semantic_scholar} />
          <DbCell label="CrossRef" value={counts.crossref} />
        </div>

        <div className="prisma-funnel">
          <Arrow label="deduplication" />
          <Stage count={counts.after_dedup} label="Unique records" />
          <Arrow label="quantitative filter" />
          <Stage count={counts.after_quant} label="Quantitative evidence" />
          <Arrow label="kinetic filter" />
          <Stage count={finalCount} label="Included" final />
        </div>
      </div>

      <div className="prisma-state">
        <span className={`state-dot ${state}`} />
        <span>{state}</span>
        {message && <span>· {message}</span>}
      </div>
    </div>
  );
}
