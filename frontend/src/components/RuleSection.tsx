import { useEffect, useState } from "react";
import { api } from "../api";
import type { Bucket, ConditionType, RuleCondition, UpdateBucketResult } from "../types";
import { CONDITION_TYPE_LABELS, emptyConditionFor } from "../ruleFormat";
import { ConditionTree } from "./ConditionTree";
import { Plus, X } from "./icons";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Checkbox } from "./ui/checkbox";
import { Badge } from "./ui/badge";
import { Textarea } from "./ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

const CONDITION_TYPES: ConditionType[] = [
  "keyword",
  "sender",
  "gmail_label",
  "header_present",
  "time_range",
  "extracted_field",
  "recipient_count",
  "is_reply",
  "has_attachment",
];

interface Props {
  bucket: Bucket;
  onSaved: (result?: UpdateBucketResult) => void;
}

export function RuleSection({ bucket, onSaved }: Props) {
  const [logic, setLogic] = useState<"AND" | "OR" | "NOT">("AND");
  const [conditions, setConditions] = useState<RuleCondition[]>([]);
  const [adding, setAdding] = useState(false);
  const [draftType, setDraftType] = useState<ConditionType>("keyword");
  const [draft, setDraft] = useState<RuleCondition>(emptyConditionFor("keyword"));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState(bucket.description ?? "");
  const [savingDescription, setSavingDescription] = useState(false);
  const [descriptionError, setDescriptionError] = useState<string | null>(null);

  const [savingMode, setSavingMode] = useState(false);
  const [modeError, setModeError] = useState<string | null>(null);

  const [matchInfo, setMatchInfo] = useState<{ matched: number; evaluated: number } | null>(null);

  useEffect(() => {
    setLogic(bucket.rule_logic ?? "AND");
    setConditions(bucket.rule_conditions ?? []);
    setAdding(false);
    setError(null);
  }, [bucket.id, bucket.rule_conditions, bucket.rule_logic, bucket.rule_version]);

  useEffect(() => {
    setDescriptionDraft(bucket.description ?? "");
    setEditingDescription(false);
    setDescriptionError(null);
    setMatchInfo(null);
  }, [bucket.id, bucket.description]);

  async function saveDescription() {
    setSavingDescription(true);
    setDescriptionError(null);
    try {
      const result = await api.updateBucket(bucket.id, { description: descriptionDraft.trim() });
      setMatchInfo(
        result.matched !== undefined && result.evaluated !== undefined
          ? { matched: result.matched, evaluated: result.evaluated }
          : null,
      );
      setEditingDescription(false);
      onSaved(result);
    } catch {
      setDescriptionError("Could not save criteria.");
    } finally {
      setSavingDescription(false);
    }
  }

  async function setMode(mode: "deterministic" | "semantic") {
    if (mode === bucket.mode || savingMode) return;
    setSavingMode(true);
    setModeError(null);
    try {
      const result = await api.updateBucket(bucket.id, { mode });
      setMatchInfo(
        result.matched !== undefined && result.evaluated !== undefined
          ? { matched: result.matched, evaluated: result.evaluated }
          : null,
      );
      onSaved(result);
    } catch {
      setModeError("Could not switch mode.");
    } finally {
      setSavingMode(false);
    }
  }

  const dirty =
    logic !== (bucket.rule_logic ?? "AND") ||
    JSON.stringify(conditions) !== JSON.stringify(bucket.rule_conditions ?? []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const result = await api.updateRule(bucket.id, logic, conditions);
      setMatchInfo({ matched: result.matched, evaluated: result.evaluated });
      onSaved();
    } catch {
      setError("Could not save rule.");
    } finally {
      setSaving(false);
    }
  }

  function addCondition() {
    setConditions((prev) => [...prev, draft]);
    setAdding(false);
    setDraftType("keyword");
    setDraft(emptyConditionFor("keyword"));
  }

  function removeCondition(i: number) {
    setConditions((prev) => prev.filter((_, idx) => idx !== i));
  }

  return (
    <div>
      <div className="mb-3">
        <div className="flex rounded-md border p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setMode("semantic")}
            disabled={savingMode}
            className={`flex-1 rounded-[5px] px-2 py-1 font-medium transition ${
              bucket.mode !== "deterministic"
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            AI judgment
          </button>
          <button
            type="button"
            onClick={() => setMode("deterministic")}
            disabled={savingMode}
            className={`flex-1 rounded-[5px] px-2 py-1 font-medium transition ${
              bucket.mode === "deterministic"
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Fixed rule
          </button>
        </div>
        {modeError && <p className="mt-1 text-xs text-destructive">{modeError}</p>}
      </div>

      {bucket.mode !== "deterministic" && (
        <div className="mb-4 rounded-md bg-accent p-3 text-xs text-accent-foreground">
          <p className="font-medium">AI judgment, not a fixed rule</p>
          <p className="mt-1 text-accent-foreground/80">
            Every thread is individually judged by an LLM against this criteria — nothing is
            pattern-matched.
          </p>
          <div className="mt-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-medium uppercase tracking-wide text-accent-foreground/60">
                Criteria
              </p>
              {!editingDescription && (
                <button
                  type="button"
                  onClick={() => setEditingDescription(true)}
                  className="text-[10px] font-medium text-accent-foreground/70 underline-offset-2 hover:underline"
                >
                  Edit
                </button>
              )}
            </div>
            {editingDescription ? (
              <div className="mt-1 space-y-1.5">
                <Textarea
                  className="min-h-16 bg-background text-xs"
                  value={descriptionDraft}
                  onChange={(e) => setDescriptionDraft(e.target.value)}
                  placeholder="Describe what belongs in this bucket…"
                  autoFocus
                />
                {descriptionError && <p className="text-xs text-destructive">{descriptionError}</p>}
                <div className="flex gap-1.5">
                  <Button size="sm" className="h-7 text-xs" onClick={saveDescription} disabled={savingDescription}>
                    {savingDescription ? "Saving…" : "Save"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => {
                      setDescriptionDraft(bucket.description ?? "");
                      setEditingDescription(false);
                      setDescriptionError(null);
                    }}
                    disabled={savingDescription}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="mt-0.5">{bucket.description || "No criteria set yet."}</p>
            )}
          </div>
          {matchInfo && (
            <p className="mt-2 text-accent-foreground/80">
              {matchInfo.matched === 0
                ? `Ran against ${matchInfo.evaluated} thread${matchInfo.evaluated === 1 ? "" : "s"} — none matched.`
                : `Matched ${matchInfo.matched} of ${matchInfo.evaluated} threads.`}
            </p>
          )}
          {bucket.mode_rationale && (
            <div className="mt-2">
              <p className="text-[10px] font-medium uppercase tracking-wide text-accent-foreground/60">
                Why AI judgment, not a rule
              </p>
              <p className="mt-0.5">{bucket.mode_rationale}</p>
            </div>
          )}
        </div>
      )}

      {bucket.mode === "deterministic" && (
        <>
          {conditions.length === 0 && (
            <p className="mb-3 text-xs text-muted-foreground">
              No conditions yet — this bucket won't match anything until you add one below.
            </p>
          )}

          <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="shrink-0">Match</span>
            <Select value={logic} onValueChange={(v) => setLogic(v as "AND" | "OR" | "NOT")}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="AND">ALL of these</SelectItem>
                <SelectItem value="OR">ANY of these</SelectItem>
                <SelectItem value="NOT">NOT this (single condition)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <ul className="space-y-1.5">
            {conditions.map((c, i) => (
              <li
                key={i}
                className="group flex items-start justify-between gap-2 rounded-md bg-muted/60 px-2.5 py-1.5"
              >
                <span className="min-w-0 break-words text-xs text-foreground/80">
                  <ConditionTree condition={c} collapsible />
                </span>
                <button
                  type="button"
                  onClick={() => removeCondition(i)}
                  className="shrink-0 text-muted-foreground opacity-0 transition hover:text-destructive group-hover:opacity-100"
                  aria-label="Remove condition"
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
            {conditions.length === 0 && <li className="text-xs text-muted-foreground">No conditions yet.</li>}
          </ul>

          {adding ? (
            <div className="mt-3 space-y-2 rounded-md border bg-muted/30 p-2.5">
              <Select
                value={draftType}
                onValueChange={(v) => {
                  const t = v as ConditionType;
                  setDraftType(t);
                  setDraft(emptyConditionFor(t));
                }}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONDITION_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {CONDITION_TYPE_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <ConditionFields type={draftType} value={draft} onChange={setDraft} />

              <div className="flex gap-1.5">
                <Button size="sm" className="flex-1" onClick={addCondition}>
                  Add
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAdding(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAdding(true)}
              className="mt-3 gap-1 border-dashed text-muted-foreground"
            >
              <Plus className="h-3 w-3" />
              Add condition
            </Button>
          )}

          {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

          {matchInfo && !dirty && (
            <p className="mt-2 text-xs text-muted-foreground">
              {matchInfo.matched === 0
                ? `Ran against ${matchInfo.evaluated} thread${matchInfo.evaluated === 1 ? "" : "s"} — none matched.`
                : `Matched ${matchInfo.matched} of ${matchInfo.evaluated} threads.`}
            </p>
          )}

          {dirty && (
            <Button className="mt-4 w-full" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

function ConditionFields({
  type,
  value,
  onChange,
}: {
  type: ConditionType;
  value: RuleCondition;
  onChange: (v: RuleCondition) => void;
}) {
  const set = (patch: Partial<RuleCondition>) => onChange({ ...value, ...patch });
  const OPS = [">=", "<=", ">", "<", "==", "!="] as const;

  const OpSelect = ({ value: op, onChange: setOp }: { value: string; onChange: (v: string) => void }) => (
    <Select value={op} onValueChange={setOp}>
      <SelectTrigger className="h-8 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {OPS.map((o) => (
          <SelectItem key={o} value={o}>
            {o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  switch (type) {
    case "keyword":
      return (
        <>
          <Input
            className="h-8 text-xs"
            placeholder="keywords, comma separated"
            value={((value.any_of as string[]) ?? []).join(", ")}
            onChange={(e) =>
              set({ any_of: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
            }
          />
          <div className="flex gap-3 text-[11px] text-muted-foreground">
            {(["subject", "snippet", "body"] as const).map((f) => (
              <label key={f} className="flex items-center gap-1.5">
                <Checkbox
                  checked={((value.fields as string[]) ?? []).includes(f)}
                  onCheckedChange={(checked) => {
                    const cur = new Set((value.fields as string[]) ?? []);
                    if (checked) cur.add(f);
                    else cur.delete(f);
                    set({ fields: Array.from(cur) });
                  }}
                />
                {f}
              </label>
            ))}
          </div>
        </>
      );
    case "sender":
      return (
        <>
          <Input
            className="h-8 text-xs"
            placeholder="domain, e.g. news.example.com"
            value={(value.domain as string) ?? ""}
            onChange={(e) => set({ domain: e.target.value || undefined })}
          />
          <Input
            className="h-8 text-xs"
            placeholder="exact email (optional)"
            value={(value.email as string) ?? ""}
            onChange={(e) => set({ email: e.target.value || undefined })}
          />
          <Input
            className="h-8 text-xs"
            placeholder="list_id (optional)"
            value={(value.list_id as string) ?? ""}
            onChange={(e) => set({ list_id: e.target.value || undefined })}
          />
        </>
      );
    case "gmail_label":
      return (
        <Input
          className="h-8 text-xs"
          placeholder="label, e.g. IMPORTANT"
          value={(value.label as string) ?? ""}
          onChange={(e) => set({ label: e.target.value })}
        />
      );
    case "header_present":
      return (
        <Input
          className="h-8 text-xs"
          placeholder="header name, e.g. List-Unsubscribe"
          value={(value.header as string) ?? ""}
          onChange={(e) => set({ header: e.target.value })}
        />
      );
    case "time_range":
      return (
        <>
          <Input
            type="datetime-local"
            className="h-8 text-xs"
            value={(value.start as string) ?? ""}
            onChange={(e) => set({ start: e.target.value || undefined })}
          />
          <Input
            type="datetime-local"
            className="h-8 text-xs"
            value={(value.end as string) ?? ""}
            onChange={(e) => set({ end: e.target.value || undefined })}
          />
        </>
      );
    case "extracted_field":
      return (
        <>
          <Input
            className="h-8 text-xs"
            placeholder="field name"
            value={(value.field as string) ?? ""}
            onChange={(e) => set({ field: e.target.value })}
          />
          <OpSelect value={(value.op as string) ?? "=="} onChange={(op) => set({ op })} />
          <Input
            className="h-8 text-xs"
            placeholder="value"
            value={String(value.value ?? "")}
            onChange={(e) => set({ value: e.target.value })}
          />
        </>
      );
    case "recipient_count":
      return (
        <>
          <OpSelect value={(value.op as string) ?? ">="} onChange={(op) => set({ op })} />
          <Input
            type="number"
            className="h-8 text-xs"
            value={Number(value.value ?? 0)}
            onChange={(e) => set({ value: Number(e.target.value) })}
          />
        </>
      );
    case "is_reply":
    case "has_attachment":
      return (
        <Select value={String(value.value ?? true)} onValueChange={(v) => set({ value: v === "true" })}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="true">Yes</SelectItem>
            <SelectItem value="false">No</SelectItem>
          </SelectContent>
        </Select>
      );
    case "group":
      return (
        <Badge variant="outline" className="text-[11px]">
          Nested groups can't be authored here yet — remove and re-add as simple conditions.
        </Badge>
      );
  }
}
