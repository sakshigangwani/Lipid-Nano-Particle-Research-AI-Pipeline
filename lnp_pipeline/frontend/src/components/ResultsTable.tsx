import { useMemo, useState } from "react";
import type { LLMVerdict, PaperRecord, SortKey } from "../types";
import PaperRow from "./PaperRow";

interface Props {
  papers: PaperRecord[];
  // Label + colour for the first summary card. Defaults to the "Included" view.
  primaryLabel?: string;
  emptyMessage?: string;
}

type Filter = "all" | LLMVerdict | "rescued";

export default function ResultsTable({
  papers,
  primaryLabel = "Included",
  emptyMessage = "No papers passed the filters for this step.",
}: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [filter, setFilter] = useState<Filter>("all");

  const totals = useMemo(() => {
    const t = {
      all: papers.length,
      include: 0,
      borderline: 0,
      exclude: 0,
      skipped: 0,
      error: 0,
      rescued: 0,
    };
    for (const p of papers) {
      t[p.llm_verdict] = (t[p.llm_verdict] ?? 0) + 1;
      if (p.caption_rescued) t.rescued += 1;
    }
    return t;
  }, [papers]);

  const filtered = useMemo(() => {
    let arr = [...papers];
    if (filter === "rescued") arr = arr.filter((p) => p.caption_rescued);
    else if (filter !== "all") arr = arr.filter((p) => p.llm_verdict === filter);
    arr.sort((a, b) => {
      if (sortKey === "score") {
        const al = a.llm_score ?? -1;
        const bl = b.llm_score ?? -1;
        if (bl !== al) return bl - al;
        return b.score - a.score;
      }
      if (sortKey === "year") return (b.year ?? 0) - (a.year ?? 0);
      return a.title.localeCompare(b.title);
    });
    return arr;
  }, [papers, filter, sortKey]);

  if (papers.length === 0) {
    return <div className="empty-state">{emptyMessage}</div>;
  }

  const filterBtn = (key: Filter, label: string, count: number) => (
    <button
      key={key}
      className={`filter-btn ${filter === key ? "active" : ""}`}
      onClick={() => setFilter(key)}
    >
      {label} · {count}
    </button>
  );

  return (
    <>
      <div className="results-summary">
        <div className="stat-card">
          <div className="stat-value blue">{papers.length}</div>
          <div className="stat-label">{primaryLabel}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value green">{totals.include}</div>
          <div className="stat-label">LLM: include</div>
        </div>
        <div className="stat-card">
          <div className="stat-value amber">{totals.borderline}</div>
          <div className="stat-label">LLM: borderline</div>
        </div>
        <div className="stat-card">
          {totals.exclude > 0 ? (
            <>
              <div className="stat-value slate">{totals.exclude}</div>
              <div className="stat-label">LLM: excluded</div>
            </>
          ) : (
            <>
              <div className="stat-value slate">{totals.rescued}</div>
              <div className="stat-label">Caption rescues</div>
            </>
          )}
        </div>
      </div>

      <div className="toolbar">
        {filterBtn("all", "All", totals.all)}
        {filterBtn("include", "Include", totals.include)}
        {totals.borderline > 0 && filterBtn("borderline", "Borderline", totals.borderline)}
        {totals.exclude > 0 && filterBtn("exclude", "Excluded", totals.exclude)}
        {totals.rescued > 0 && filterBtn("rescued", "Caption-rescued", totals.rescued)}
        <div className="spacer" />
        <label
          style={{
            fontSize: "0.72rem",
            fontWeight: 700,
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            color: "var(--ink-400)",
          }}
        >
          Sort
        </label>
        <select
          className="sort-select"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
        >
          <option value="score">Score (LLM ↘)</option>
          <option value="year">Year (newest)</option>
          <option value="title">Title (A→Z)</option>
        </select>
      </div>

      <div className="studies-list">
        {filtered.map((p, i) => (
          <PaperRow key={p.doi ?? p.pmid ?? `${i}-${p.title}`} paper={p} />
        ))}
      </div>
    </>
  );
}
