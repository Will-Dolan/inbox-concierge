import { useRef, useState } from "react";
import { api, ApiError, pollJob } from "../api";
import type { AgentStep, CreateBucketResult, JobStatus } from "../types";
import { Sparkles } from "./icons";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

type Phase = "form" | "thinking" | "done" | "error";
type Classifier = "llm" | "rules";

export function BucketEditorDialog({ open, onOpenChange, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [classifier, setClassifier] = useState<Classifier>("rules");
  const [phase, setPhase] = useState<Phase>("form");
  const [result, setResult] = useState<CreateBucketResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const submittingRef = useRef(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || phase !== "form" || submittingRef.current) return;
    submittingRef.current = true;
    setPhase("thinking");
    setError(null);
    setSteps([]);
    try {
      const { job_id } = await api.createBucket(name.trim(), description.trim(), classifier);
      const final: JobStatus<CreateBucketResult> = await pollJob(job_id, {
        intervalMs: 1200,
        onTick: (s) => setSteps(s.progress ?? []),
      });
      if (final.status === "done" && final.result) {
        setResult(final.result);
        setPhase("done");
        onCreated();
      } else {
        setError(final.error ?? "Something went wrong.");
        setPhase("error");
      }
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "A bucket with that name already exists."
          : "Could not reach the server.",
      );
      setPhase("error");
    } finally {
      submittingRef.current = false;
    }
  }

  function reset() {
    setName("");
    setDescription("");
    setClassifier("rules");
    setPhase("form");
    setResult(null);
    setError(null);
    setSteps([]);
    submittingRef.current = false;
  }

  function handleClose() {
    onOpenChange(false);
    reset();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          handleClose();
        } else {
          onOpenChange(next);
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogTitle>New bucket</DialogTitle>

        {phase === "form" && (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="bucket-name">Name</Label>
              <Input
                id="bucket-name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Streaming Deals"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bucket-description">Description</Label>
              <Textarea
                id="bucket-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What kind of email belongs here? Be specific - the agent uses this to explore your inbox."
                rows={3}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Classifier</Label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setClassifier("rules")}
                  className={`rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                    classifier === "rules"
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-input text-muted-foreground hover:bg-accent"
                  }`}
                >
                  <div className="font-medium">Rules</div>
                  <div className="text-xs text-muted-foreground">
                    Agent searches your inbox for a pattern. Free and instant once found.
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setClassifier("llm")}
                  className={`rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                    classifier === "llm"
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-input text-muted-foreground hover:bg-accent"
                  }`}
                >
                  <div className="font-medium">LLM</div>
                  <div className="text-xs text-muted-foreground">
                    Skip rule search - an LLM judges each thread directly.
                  </div>
                </button>
              </div>
            </div>
            <Button type="submit" disabled={!name.trim() || phase !== "form"} className="w-full">
              Create bucket
            </Button>
          </form>
        )}

        {phase === "thinking" && (
          <div>
            <div className="flex flex-col items-center gap-2 py-4 text-center">
              <Sparkles className="h-6 w-6 animate-pulse text-primary" />
              <p className="text-sm font-medium text-foreground">
                {classifier === "rules" ? "Agent is exploring your inbox…" : "Setting up AI-judgment classification…"}
              </p>
            </div>
            <ol className="mt-2 max-h-64 space-y-2 overflow-y-auto rounded-lg border bg-muted/40 p-3">
              {steps.length === 0 ? (
                <li className="text-xs text-muted-foreground">Starting up…</li>
              ) : (
                steps.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-foreground/80">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span>{s.label}</span>
                  </li>
                ))
              )}
            </ol>
          </div>
        )}

        {phase === "done" && result && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant={result.mode === "deterministic" ? "default" : "secondary"}>
                {result.mode === "deterministic" ? "Rule found" : "Using AI judgment"}
              </Badge>
              {result.precision != null && (
                <span className="text-xs text-muted-foreground">
                  {(result.precision * 100).toFixed(0)}% precision on {result.validated_on} samples
                </span>
              )}
            </div>
            <p className="text-sm text-foreground/80">{result.rationale}</p>
            <Button className="w-full" onClick={handleClose}>
              Done
            </Button>
          </div>
        )}

        {phase === "error" && (
          <div className="space-y-3">
            <p className="text-sm text-destructive">{error}</p>
            <Button className="w-full" onClick={reset}>
              Try again
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
