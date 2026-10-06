import type {
  AccessFilter,
  EvidenceFilter,
  ExportFormat,
  ResultTab,
  RunResults,
  StudyFilter,
  RunStatus,
  StepInfo,
} from "../types";

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json() as Promise<T>;
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json() as Promise<T>;
}

export function getSteps(): Promise<StepInfo[]> {
  return jget<StepInfo[]>("/api/steps");
}

export function startSearch(step_id: number): Promise<{ run_id: string }> {
  return jpost<{ run_id: string }>("/api/search", { step_id });
}

export function getStatus(run_id: string): Promise<RunStatus> {
  return jget<RunStatus>(`/api/runs/${run_id}/status`);
}

export function getResults(run_id: string): Promise<RunResults> {
  return jget<RunResults>(`/api/runs/${run_id}/results`);
}

export function exportUrl(
  run_id: string,
  format: ExportFormat,
  which: ResultTab = "included",
  studyType: StudyFilter = "all",
  access: AccessFilter = "all",
  evidence: EvidenceFilter = "all"
): string {
  return `/api/runs/${run_id}/export?format=${format}&which=${which}&study_type=${studyType}&access=${access}&evidence=${evidence}`;
}
