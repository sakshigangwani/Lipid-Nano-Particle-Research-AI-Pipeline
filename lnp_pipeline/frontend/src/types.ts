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
  openalex: number;
  biorxiv: number;
  arxiv: number;
  total_raw: number;
  after_dedup: number;
  after_kinetic: number;
  caption_rescued: number;
  llm_scored: number;
  final: number;
}

export type LLMVerdict = "include" | "borderline" | "exclude" | "skipped" | "error";

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
  matched_kinetic_terms: string[];
  matched_signal_phrases: string[];
  semantic_kinetic_match: boolean;
  is_review: boolean;
  study_type: StudyType;
  study_type_source?: "llm" | "keywords";
  access: AccessType;
  oa_status: string | null;
  oa_url: string | null;
  score: number;
  llm_score: number | null;
  llm_verdict: LLMVerdict;
  llm_rationale: string;
  caption_rescued: boolean;
  supplementary_rescued: boolean;
  kinetic_unverified?: boolean;
}

export interface RunResults {
  run_id: string;
  step_id: number;
  step_name: string;
  counts: PrismaCounts;
  // LLM-included set (the funnel's "final" count).
  papers: PaperRecord[];
  // Every paper sent to the LLM (pre-LLM-scored set), including LLM-excluded ones.
  candidates: PaperRecord[];
}

export type ResultTab = "included" | "candidates";

export type StudyType = "in_vitro" | "in_vivo" | "both" | "unclassified";
// "both" papers appear under both In vitro and In vivo.
export type StudyFilter = "all" | "in_vitro" | "in_vivo" | "unclassified";

export type AccessType = "open" | "closed" | "unknown";
export type AccessFilter = "all" | AccessType;
// "supplementary_only": evidence found only in supporting/supplementary material.
export type EvidenceFilter = "all" | "supplementary_only";

export type SortKey = "score" | "year" | "title";
export type ExportFormat = "xlsx" | "csv" | "json" | "md";
