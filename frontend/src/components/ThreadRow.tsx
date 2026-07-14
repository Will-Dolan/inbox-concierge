import clsx from "clsx";
import { X } from "./icons";
import type { Bucket, Thread } from "../types";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
}

interface Props {
  thread: Thread;
  bucketsByName: Map<string, Bucket>;
  activeBucketName: string | null;
  expanded: boolean;
  onToggle: (thread: Thread) => void;
  onCorrect: (thread: Thread, bucketName: string, action: "add" | "remove") => void;
}

export function ThreadRow({
  thread,
  bucketsByName,
  activeBucketName,
  expanded,
  onToggle,
  onCorrect,
}: Props) {
  const showAddToActive = activeBucketName !== null && !thread.tags.includes(activeBucketName);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onToggle(thread)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onToggle(thread);
      }}
      className={clsx(
        "group cursor-pointer rounded-lg border px-3.5 py-2.5 shadow-sm transition hover:border-primary/40",
        thread.unread ? "bg-card" : "bg-card/60",
        expanded && "rounded-b-none border-b-0 border-primary/50",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <p
          className={clsx(
            "min-w-0 truncate text-sm",
            thread.unread ? "font-medium text-foreground" : "font-normal text-muted-foreground",
          )}
        >
          {thread.unread && (
            <span className="mr-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-primary align-middle" />
          )}
          {thread.subject || "(no subject)"}
        </p>
        <span className="shrink-0 text-xs text-muted-foreground">
          {formatDate(thread.latest_internal_date)}
        </span>
      </div>
      <div className="mt-1 flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
          <span className="font-medium text-foreground/70">
            {thread.sender_domain || "unknown sender"}
          </span>
          {thread.snippet && <span> - {thread.snippet}</span>}
        </p>
        <div className="flex max-w-[65%] flex-wrap items-center justify-end gap-1.5">
          {thread.tags.map((tagName) => {
            const bucket = bucketsByName.get(tagName);
            const rationale =
              bucket?.mode === "deterministic" && bucket.rule_rationale
                ? bucket.rule_rationale
                : bucket?.mode === "semantic"
                  ? `Classified by AI: matches "${bucket.name}" — ${bucket.description ?? ""}`
                  : undefined;
            return (
              <Tooltip key={tagName} delayDuration={200}>
                <TooltipTrigger asChild>
                  <Badge variant="secondary" className="group/tag relative font-medium">
                    <span>{tagName}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${tagName} tag`}
                      className="absolute inset-y-0 right-0 flex w-5 items-center justify-center rounded-r-md bg-secondary text-black opacity-0 transition-opacity group-hover/tag:opacity-100"
                      onClick={(e) => {
                        e.stopPropagation();
                        onCorrect(thread, tagName, "remove");
                      }}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                </TooltipTrigger>
                {rationale && <TooltipContent className="max-w-xs">{rationale}</TooltipContent>}
              </Tooltip>
            );
          })}
          {showAddToActive && activeBucketName && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-5 border-dashed px-1.5 text-[11px] font-medium text-muted-foreground opacity-0 transition group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onCorrect(thread, activeBucketName, "add");
              }}
            >
              + {activeBucketName}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
