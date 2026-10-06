import { useState } from "react";
import type { LLMVerdict, PaperRecord, StudyType } from "../types";
import MatchedTerms from "./MatchedTerms";

const STUDY_LABELS: Record<StudyType, string> = {
  in_vitro: "in vitro",
  in_vivo: "in vivo",
  both: "in vitro + in vivo",
  unclassified: "unclassified",
};

interface Props {
  paper: PaperRecord;
}

function verdictClass(v: LLMVerdict): string {
  return `relevance-badge ${v}`;
}

function scoreBreakdown(p: PaperRecord) {
  const k = (Math.min(p.matched_kinetic_terms.length, 5) / 5) * 0.45;
  const s = (Math.min(p.matched_signal_phrases.length, 4) / 4) * 0.45;
  const d = (Math.min(Math.max(p.source_dbs.length - 1, 0), 3) / 3) * 0.1;
  return { k, s, d };
}

function Bar({
  kind,
  value,
  cap,
}: {
  kind: "k" | "s" | "d";
  value: number;
  cap: number;
}) {
  const pct = Math.min(100, (value / cap) * 100);
  const label = { k: "Kinetic", s: "Signal", d: "Multi-DB" }[kind];
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className={`bar-fill ${kind}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="bar-value">+{value.toFixed(2)}</span>
    </div>
  );
}

export default function PaperRow({ paper }: Props) {
  const [open, setOpen] = useState(false);
  const doiUrl = paper.doi ? `https://doi.org/${paper.doi}` : null;
  const pmidUrl = paper.pmid
    ? `https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`
    : null;
  const { k, s, d } = scoreBreakdown(paper);

  const titleHtml = doiUrl ? (
    <a href={doiUrl} target="_blank" rel="noreferrer">
      {paper.title || "(no title)"}
    </a>
  ) : (
    paper.title || "(no title)"
  );

  const llmPct = paper.llm_score != null ? Math.round(paper.llm_score * 100) : null;

  return (
    <div className="study-card">
      <div className="study-header">
        <div className="study-title">{titleHtml}</div>
        <div className="badges">
          {paper.study_type && paper.study_type !== "unclassified" && (
            <span
              className="fig-badge study"
              title={
                paper.study_type_source === "llm"
                  ? "Study type, decided by the LLM from the abstract and captions"
                  : "Study type, from keyword matching (LLM classification unavailable for this paper)"
              }
            >
              {STUDY_LABELS[paper.study_type]}
            </span>
          )}
          {paper.access === "open" && (
            <a
              className="fig-badge oa"
              href={paper.oa_url ?? undefined}
              target="_blank"
              rel="noreferrer"
              title={`Open access${paper.oa_status ? ` (${paper.oa_status})` : ""}${
                paper.oa_url ? " — click for the free full text" : ""
              }`}
            >
              open access
            </a>
          )}
          {paper.access === "closed" && (
            <span className="fig-badge closed" title="Closed access (paywalled), per OpenAlex">
              closed
            </span>
          )}
          {paper.is_review && (
            <span
              className="fig-badge"
              title="Review article — synthesizes other papers' data rather than reporting its own; exempt from the kinetic-evidence requirement"
            >
              review
            </span>
          )}
          {paper.caption_rescued && (
            <span
              className="fig-badge"
              title="Rescued by figure/table captions — abstract didn't have the kinetic match"
            >
              fig
            </span>
          )}
          {paper.supplementary_rescued && (
            <span
              className="fig-badge suppl"
              title="Rescued by supplementary material — abstract didn't have the kinetic match, but the paper's supplementary file content did"
            >
              suppl
            </span>
          )}
          {paper.kinetic_unverified && (
            <span
              className="fig-badge suppl"
              title="No full text available, so kinetic data couldn't be checked — passed because the abstract shows this step was measured"
            >
              unverified
            </span>
          )}
          {paper.semantic_kinetic_match && (
            <span
              className="fig-badge suppl"
              title="Kinetic evidence found via semantic similarity, not an exact keyword/regex match"
            >
              semantic
            </span>
          )}
          <span className={verdictClass(paper.llm_verdict)}>
            {paper.llm_verdict}
            {paper.llm_score != null ? ` · ${paper.llm_score.toFixed(2)}` : ""}
          </span>
        </div>
      </div>

      <div className="study-meta">
        {paper.year && (
          <span className="study-meta-item">
            <strong>Year:</strong> {paper.year}
          </span>
        )}
        {paper.journal && (
          <span className="study-meta-item">
            <strong>Journal:</strong>{" "}
            {paper.journal.length > 50
              ? paper.journal.slice(0, 50) + "…"
              : paper.journal}
          </span>
        )}
        {paper.authors.length > 0 && (
          <span className="study-meta-item">
            <strong>Authors:</strong>{" "}
            {paper.authors.slice(0, 3).join(", ")}
            {paper.authors.length > 3 ? ", et al." : ""}
          </span>
        )}
        {paper.source_dbs.length > 0 && (
          <span className="study-meta-item">
            <strong>Source:</strong>
            <span className="source-pills" style={{ marginLeft: 4 }}>
              {paper.source_dbs.map((db) => (
                <span key={db} className="source-pill">
                  {db}
                </span>
              ))}
            </span>
          </span>
        )}
      </div>

      <div className="study-footer">
        {llmPct != null && (
          <div className="confidence-bar">
            <div className="confidence-track">
              <div
                className={`confidence-fill ${paper.llm_verdict === "include" ? "green" : ""}`}
                style={{ width: `${llmPct}%` }}
              />
            </div>
            <span className="confidence-text">{llmPct}% LLM confidence</span>
          </div>
        )}
        <button className="study-toggle" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide details" : "Show details"}
        </button>
      </div>

      {open && (
        <div className="study-details">
          <div className="detail-block">
            {paper.llm_rationale && (
              <div className="llm-rationale">
                <h4>OpenAI verdict</h4>
                <p>{paper.llm_rationale}</p>
              </div>
            )}
            <h4 style={{ marginTop: 14 }}>Abstract</h4>
            {paper.abstract ? (
              <div className="abstract-text">{paper.abstract}</div>
            ) : (
              <div className="empty-state" style={{ padding: 12 }}>
                No abstract available.
              </div>
            )}
            <div
              style={{
                display: "flex",
                gap: 10,
                marginTop: 10,
                flexWrap: "wrap",
              }}
            >
              {doiUrl && (
                <a className="btn-ghost" href={doiUrl} target="_blank" rel="noreferrer">
                  DOI ↗
                </a>
              )}
              {pmidUrl && (
                <a className="btn-ghost" href={pmidUrl} target="_blank" rel="noreferrer">
                  PubMed ↗
                </a>
              )}
            </div>
            <MatchedTerms
              kinetic={paper.matched_kinetic_terms}
              signal={paper.matched_signal_phrases}
            />
          </div>
          <div className="score-breakdown">
            <div className="total">
              <span className="label">Composite score</span>
              <span className="value">{paper.score.toFixed(2)}</span>
            </div>
            <Bar kind="k" value={k} cap={0.45} />
            <Bar kind="s" value={s} cap={0.45} />
            <Bar kind="d" value={d} cap={0.1} />
            <div
              style={{
                marginTop: 10,
                fontSize: 11,
                color: "var(--ink-400)",
                fontStyle: "italic",
                lineHeight: 1.4,
              }}
            >
              Kinetic / signal each cap at 0.45; multi-database
              corroboration at 0.10.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
