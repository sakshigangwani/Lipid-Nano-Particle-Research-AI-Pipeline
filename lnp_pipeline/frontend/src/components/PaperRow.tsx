import { useState } from "react";
import type { PaperRecord } from "../types";
import MatchedTerms from "./MatchedTerms";

interface Props {
  paper: PaperRecord;
}

function scoreClass(score: number): string {
  if (score < 0.4) return "score-chip score-red";
  if (score <= 0.7) return "score-chip score-amber";
  return "score-chip score-green";
}

// Mirrors backend utils/scoring.py:score_paper
function scoreBreakdown(p: PaperRecord) {
  const q = (Math.min(p.matched_quant_terms.length, 5) / 5) * 0.3;
  const k = (Math.min(p.matched_kinetic_terms.length, 5) / 5) * 0.3;
  const s = (Math.min(p.matched_signal_phrases.length, 4) / 4) * 0.3;
  const d = (Math.min(Math.max(p.source_dbs.length - 1, 0), 3) / 3) * 0.1;
  return { q, k, s, d };
}

function Bar({ kind, value, cap }: { kind: "q" | "k" | "s" | "d"; value: number; cap: number }) {
  const pct = Math.min(100, (value / cap) * 100);
  const label = { q: "Quant", k: "Kinetic", s: "Signal", d: "Multi-DB" }[kind];
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track"><div className={`bar-fill ${kind}`} style={{ width: `${pct}%` }} /></div>
      <span className="bar-value">+{value.toFixed(2)}</span>
    </div>
  );
}

export default function PaperRow({ paper }: Props) {
  const [open, setOpen] = useState(false);
  const doiUrl = paper.doi ? `https://doi.org/${paper.doi}` : null;
  const pmidUrl = paper.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/` : null;
  const { q, k, s, d } = scoreBreakdown(paper);

  return (
    <>
      <tr
        className={`paper ${open ? "expanded" : ""}`}
        onClick={() => setOpen((v) => !v)}
      >
        <td><span className={scoreClass(paper.score)}>{paper.score.toFixed(2)}</span></td>
        <td className="title-cell">
          <div className="title-text">{paper.title || "(no title)"}</div>
          {paper.authors.length > 0 && (
            <div className="title-authors">
              {paper.authors.slice(0, 6).join(", ")}
              {paper.authors.length > 6 ? ", et al." : ""}
            </div>
          )}
        </td>
        <td className="cell-muted">{paper.year ?? ""}</td>
        <td className="cell-muted">{paper.journal ?? ""}</td>
        <td>
          <div className="source-pills">
            {paper.source_dbs.map((db) => (
              <span key={db} className="source-pill">{db}</span>
            ))}
          </div>
        </td>
        <td>
          {doiUrl ? (
            <a className="doi-link" href={doiUrl} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              {paper.doi}
            </a>
          ) : (
            <span className="cell-meta">—</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={6}>
            <div className="detail">
              <div>
                <h4>Abstract</h4>
                {paper.abstract ? (
                  <div className="abstract">{paper.abstract}</div>
                ) : (
                  <div className="empty">No abstract available.</div>
                )}
                <div className="links">
                  {doiUrl && <a href={doiUrl} target="_blank" rel="noreferrer">DOI ↗</a>}
                  {pmidUrl && <a href={pmidUrl} target="_blank" rel="noreferrer">PubMed ↗</a>}
                </div>
                <MatchedTerms
                  quant={paper.matched_quant_terms}
                  kinetic={paper.matched_kinetic_terms}
                  signal={paper.matched_signal_phrases}
                />
              </div>
              <div className="score-breakdown">
                <div className="total">
                  <span className="label">Composite score</span>
                  <span className="value">{paper.score.toFixed(2)}</span>
                </div>
                <Bar kind="q" value={q} cap={0.3} />
                <Bar kind="k" value={k} cap={0.3} />
                <Bar kind="s" value={s} cap={0.3} />
                <Bar kind="d" value={d} cap={0.1} />
                <div style={{ marginTop: 10, fontSize: 11, color: "var(--muted)", fontStyle: "italic", lineHeight: 1.4 }}>
                  Quant / kinetic / signal each cap at 0.30; multi-database corroboration at 0.10.
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
