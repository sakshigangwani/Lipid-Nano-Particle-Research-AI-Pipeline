import { useEffect, useMemo, useRef, useState } from "react";
import {
  exportUrl,
  getResults,
  getStatus,
  getSteps,
  startSearch,
} from "./api/client";
import PrismaCountsPanel from "./components/PrismaCounts";
import ResultsTable from "./components/ResultsTable";
import RunButton from "./components/RunButton";
import StepPicker from "./components/StepPicker";
import type {
  ExportFormat,
  PrismaCounts,
  RunResults,
  RunState,
  StepInfo,
} from "./types";

const EMPTY_COUNTS: PrismaCounts = {
  pubmed: 0,
  europepmc: 0,
  semantic_scholar: 0,
  crossref: 0,
  openalex: 0,
  biorxiv: 0,
  total_raw: 0,
  after_dedup: 0,
  after_quant: 0,
  after_kinetic: 0,
  caption_rescued: 0,
  llm_scored: 0,
  final: 0,
};

type Phase = 1 | 2 | 3 | 4;

function StepIndicator({ phase }: { phase: Phase }) {
  const labels = ["Select Stage", "Search", "Results"];
  return (
    <div className="step-indicator">
      {labels.map((label, i) => {
        const idx = i + 1;
        const cls =
          phase > idx ? "step completed" : phase === idx ? "step active" : "step";
        return (
          <span key={label} style={{ display: "contents" }}>
            <div className={cls}>
              <div className="step-num">{idx}</div>
              <span className="step-label">{label}</span>
            </div>
            {idx < labels.length && (
              <div
                className={`step-line ${phase > idx ? "completed" : ""}`}
              />
            )}
          </span>
        );
      })}
    </div>
  );
}

export default function App() {
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [state, setState] = useState<RunState | "idle">("idle");
  const [counts, setCounts] = useState<PrismaCounts>(EMPTY_COUNTS);
  const [results, setResults] = useState<RunResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<Date | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    getSteps()
      .then(setSteps)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  async function onRun() {
    if (selectedId == null) return;
    setError(null);
    setResults(null);
    setCounts(EMPTY_COUNTS);
    setStatusMsg(null);
    setState("running");
    setStartedAt(new Date());
    try {
      const { run_id } = await startSearch(selectedId);
      setRunId(run_id);
      startPolling(run_id);
    } catch (e) {
      setError(String(e));
      setState("idle");
    }
  }

  function startPolling(rid: string) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const s = await getStatus(rid);
        setCounts(s.counts);
        setState(s.state);
        setStatusMsg(s.message ?? null);
        if (s.state === "done") {
          window.clearInterval(pollRef.current!);
          pollRef.current = null;
          const r = await getResults(rid);
          setResults(r);
        } else if (s.state === "error") {
          window.clearInterval(pollRef.current!);
          pollRef.current = null;
        }
      } catch (e) {
        setError(String(e));
      }
    }, 1500);
  }

  const running = state === "running";
  const selectedStep = useMemo(
    () => steps.find((s) => s.id === selectedId) ?? null,
    [steps, selectedId]
  );
  const hasRun = state !== "idle" || results != null;

  const phase: Phase =
    results != null ? 4 : running ? 2 : selectedId != null ? 2 : 1;

  const statusLabel =
    state === "running"
      ? "Running search"
      : state === "done"
      ? "Run complete"
      : state === "error"
      ? "Run failed"
      : "Pipeline ready";

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand">
          <div className="navbar-logo">LNP</div>
          Lipid Nanoparticle Research Hub
          <span className="brand-sub">v1</span>
        </div>
        <div className="navbar-status">
          <div className={`status-dot ${state}`} />
          {statusLabel}
        </div>
      </nav>

      <div className="page-wrapper">
        <div className="page-header">
          <h1>LNP Literature Pipeline</h1>
          <p>
            Pick one of the seven LNP delivery-journey stages, search PubMed,
            Europe PMC, CrossRef, OpenAlex, Semantic Scholar, and bioRxiv, and
            let the agent score every paper for quantitative + time-resolved
            evidence — including a figure-caption fallback when abstracts are
            too terse.
          </p>
        </div>

        <StepIndicator phase={phase} />

        {error && <div className="alert-panel error">Error · {error}</div>}

        <div className={`dashboard ${hasRun ? "dashboard-split" : ""}`}>
          <div className="dashboard-left">
            <div className="card">
              <div className="card-title">Step 1 · Select an LNP stage</div>
              <StepPicker
                steps={steps}
                selectedId={selectedId}
                onSelect={setSelectedId}
                disabled={running}
              />
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginTop: 18,
                  paddingTop: 16,
                  borderTop: "1px solid #f1f5f9",
                  flexWrap: "wrap",
                }}
              >
                <RunButton
                  onRun={onRun}
                  running={running}
                  disabled={selectedId == null || running}
                />
                <div
                  style={{
                    fontSize: "0.78rem",
                    color: "var(--ink-400)",
                    fontWeight: 500,
                  }}
                >
                  {selectedStep
                    ? `Selected: ${selectedStep.name}`
                    : "Pick a stage to enable the run"}
                </div>
              </div>
              {runId && (
                <div
                  style={{
                    marginTop: 12,
                    fontSize: "0.72rem",
                    color: "var(--ink-400)",
                    fontFamily:
                      "'SF Mono', ui-monospace, Menlo, Consolas, monospace",
                  }}
                >
                  run_id: {runId}
                  {startedAt && (
                    <> &nbsp;·&nbsp; started: {startedAt.toLocaleTimeString()}</>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="dashboard-right">
            {(state !== "idle" || results) && (
              <PrismaCountsPanel
                counts={counts}
                state={state === "idle" ? "done" : state}
                message={statusMsg}
              />
            )}

            {results && (
              <div className="card">
                <div className="progress-header">
                  <div className="card-title" style={{ marginBottom: 0 }}>
                    Step 3 · Included papers — {results.step_name}
                  </div>
                  <div className="status-badge done">
                    {results.papers.length}{" "}
                    {results.papers.length === 1 ? "paper" : "papers"}
                  </div>
                </div>

                <div className="toolbar">
                  <span
                    style={{
                      fontSize: "0.72rem",
                      fontWeight: 700,
                      letterSpacing: "0.6px",
                      textTransform: "uppercase",
                      color: "var(--ink-400)",
                    }}
                  >
                    Export
                  </span>
                  {(["csv", "json", "md"] as ExportFormat[]).map((f) => (
                    <a
                      key={f}
                      className="btn-ghost"
                      href={exportUrl(results.run_id, f)}
                    >
                      {f.toUpperCase()}
                    </a>
                  ))}
                  <div className="spacer" />
                </div>

                <ResultsTable papers={results.papers} />
              </div>
            )}
          </div>
        </div>

        <div className="footer-note">
          Lipid Nanoparticle Literature Pipeline
          <span className="sep">·</span>
          Quantitative + kinetic evidence retrieval
        </div>
      </div>
    </>
  );
}
