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
  total_raw: 0,
  after_dedup: 0,
  after_quant: 0,
  after_kinetic: 0,
  final: 0,
};

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
    }, 1000);
  }

  const running = state === "running";
  const selectedStep = useMemo(
    () => steps.find((s) => s.id === selectedId) ?? null,
    [steps, selectedId]
  );

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead-left">
          <div className="eyebrow">LNP Delivery Pipeline</div>
          <h1>Lipid Nanoparticle Literature Pipeline</h1>
          <p className="subtitle">
            Systematic retrieval of quantitative and kinetic LNP literature across
            PubMed, Europe PMC, Semantic Scholar, and CrossRef, organised along the
            seven stages of the LNP delivery journey.
          </p>
        </div>
      </header>

      {error && <div className="error-banner">Error · {error}</div>}

      <StepPicker
        steps={steps}
        selectedId={selectedId}
        onSelect={setSelectedId}
        disabled={running}
      />

      <div className="panel">
        <div className="panel-header">
          <h2>Step 2 · Execute query</h2>
          <span className="step-label">
            {selectedStep ? `selected: ${selectedStep.name}` : "no stage selected"}
          </span>
        </div>
        <div className="actions">
          <RunButton
            onRun={onRun}
            running={running}
            disabled={selectedId == null || running}
          />
          {runId && (
            <span className="run-id">
              <span className="k">run_id:</span> {runId}
              {startedAt && (
                <>
                  <span className="k"> · started:</span> {startedAt.toLocaleTimeString()}
                </>
              )}
            </span>
          )}
        </div>
      </div>

      {(state !== "idle" || results) && (
        <PrismaCountsPanel
          counts={counts}
          state={state === "idle" ? "done" : state}
          message={statusMsg}
        />
      )}

      {results && (
        <div className="panel">
          <div className="panel-header">
            <h2>Step 3 · Included papers — {results.step_name}</h2>
            <span className="step-label">
              {results.papers.length} {results.papers.length === 1 ? "record" : "records"} · sorted by composite score
            </span>
          </div>
          <div className="export-bar" style={{ marginBottom: 16 }}>
            <span className="label">Export</span>
            {(["csv", "json", "md"] as ExportFormat[]).map((f) => (
              <a
                key={f}
                className="ghost"
                href={exportUrl(results.run_id, f)}
              >
                {f.toUpperCase()}
              </a>
            ))}
          </div>
          <ResultsTable papers={results.papers} />
        </div>
      )}

      <div className="footer-note">
        Lipid Nanoparticle Literature Pipeline
        <span className="sep">·</span>
        Quantitative + kinetic evidence retrieval
      </div>
    </div>
  );
}
