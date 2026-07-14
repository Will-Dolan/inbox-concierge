import { useEffect, useState } from "react";
import { api } from "../api";
import { Markdown } from "./Markdown";
import { Refresh } from "./icons";
import { Button } from "./ui/button";

interface Props {
  bucketId: string;
}

function formatGeneratedAt(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function DigestSection({ bucketId }: Props) {
  const [digest, setDigest] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Digests are cached server-side (digests table) - opening this section
  // doesn't cost an LLM call. Only reset local state when the bucket changes;
  // fetching still waits for a click so switching buckets doesn't itself fire
  // a request.
  useEffect(() => {
    setDigest(null);
    setGeneratedAt(null);
    setError(null);
  }, [bucketId]);

  function load(force: boolean) {
    setLoading(true);
    setError(null);
    api
      .getDigest(bucketId, force)
      .then((res) => {
        setDigest(res.digest);
        setGeneratedAt(res.generated_at);
      })
      .catch(() => setError("Could not generate a digest."))
      .finally(() => setLoading(false));
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[11px] text-muted-foreground">
          Summary of this bucket's threads.
          {digest !== null && generatedAt && ` Generated ${formatGeneratedAt(generatedAt)}.`}
        </p>
        {digest !== null && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 shrink-0 px-1.5 text-muted-foreground"
            onClick={() => load(true)}
            disabled={loading}
            aria-label="Regenerate digest"
            title="Regenerate digest"
          >
            <Refresh className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
          </Button>
        )}
      </div>
      {loading ? (
        <p className="text-xs text-muted-foreground">Summarizing…</p>
      ) : error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : digest !== null ? (
        <div className="space-y-1.5 text-xs leading-relaxed text-foreground/80">
          <Markdown text={digest} />
        </div>
      ) : (
        <Button variant="outline" size="sm" onClick={() => load(false)} className="gap-1.5">
          <Refresh className="h-3.5 w-3.5" />
          Generate digest
        </Button>
      )}
    </div>
  );
}
