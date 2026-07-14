export interface Thread {
  id: string;
  subject: string | null;
  snippet: string | null;
  sender_domain: string | null;
  latest_internal_date: string | null;
  tags: string[];
  unread: boolean;
}

export interface ThreadMessage {
  from: string | null;
  to: string | null;
  date: string;
  body: string | null;
  body_html: string | null;
}

export interface ThreadDetail extends Thread {
  messages: ThreadMessage[];
}

export interface UnsubscribeCandidate {
  sender_domain: string;
  method: "one_click" | "link" | "mailto";
  url: string;
  thread_count: number;
}

export interface Bucket {
  id: string;
  name: string;
  description: string | null;
  kind: "system" | "custom";
  mode: "deterministic" | "semantic";
  mode_source: "default" | "agent" | "user";
  rule_confidence: number | null;
  rule_rationale: string | null;
  rule_version: number | null;
  rule_summary: string | null;
  rule_logic: "AND" | "OR" | "NOT" | null;
  rule_conditions: RuleCondition[] | null;
  mode_rationale: string | null;
}

export type ConditionType =
  | "keyword"
  | "sender"
  | "gmail_label"
  | "header_present"
  | "time_range"
  | "extracted_field"
  | "recipient_count"
  | "is_reply"
  | "has_attachment"
  | "group";

export interface RuleCondition {
  type: ConditionType;
  [key: string]: unknown;
}

export interface AgentStep {
  label: string;
}

export interface JobStatus<T = unknown> {
  status: "pending" | "running" | "done" | "failed" | "not_found";
  result: T | null;
  error: string | null;
  progress: AgentStep[];
}

export interface UpdateBucketResult {
  id: string;
  mode?: "deterministic" | "semantic";
  mode_source?: "default" | "agent" | "user";
  description?: string | null;
  matched?: number;
  evaluated?: number;
  classification_job_id?: string | null;
}

export interface SyncResult {
  threads_synced: number;
  threads_classified: number;
}

export interface DigestResult {
  digest: string;
  generated_at: string | null;
}

export interface MarkReadResult {
  marked: number;
  failed: number;
}

export interface CreateBucketResult {
  bucket_id: string;
  mode: "deterministic" | "semantic";
  precision: number | null;
  validated_on: number | null;
  rationale: string;
  matched: number;
  evaluated: number;
}
