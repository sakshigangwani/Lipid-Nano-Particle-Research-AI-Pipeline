export interface StepInfo {
  id: number;
  name: string;
  description: string;
  strict_kinetic: boolean;
}

export interface PrismaCounts {
  pubmed: number;
  europepmc: number;
  semantic_scholar: number;
  crossref: number;
  total_raw: number;
  after_dedup: number;
  after_quant: number;
  after_kinetic: number;
  final: number;
}

export type RunState = "running" | "done" | "error";

export interface RunStatus {
  run_id: string;
  step_id: number;
  state: RunState;
  counts: PrismaCounts;
  message: string | null;
}

export interface PaperRecord {
  title: string;
  authors: string[];
  year: number | null;
  journal: string | null;
  doi: string | null;
  pmid: string | null;
  source_dbs: string[];
  abstract: string | null;
  matched_quant_terms: string[];
  matched_kinetic_terms: string[];
  matched_signal_phrases: string[];
  score: number;
}

export interface RunResults {
  run_id: string;
  step_id: number;
  step_name: string;
  counts: PrismaCounts;
  papers: PaperRecord[];
}

export type SortKey = "score" | "year" | "title";
export type ExportFormat = "csv" | "json" | "md";
