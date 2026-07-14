import type { ThreadDetail } from "../types";
import { EmailBody } from "./EmailBody";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface Props {
  detail: ThreadDetail | null;
  loading: boolean;
}

export function ThreadDetailPanel({ detail, loading }: Props) {
  return (
    <div className="-mt-1 mb-1 rounded-b-lg border border-t-0 bg-muted/40 px-4 py-3">
      {loading || !detail ? (
        <p className="text-xs text-muted-foreground">Loading thread…</p>
      ) : (
        <div className="space-y-4">
          {detail.messages.map((m, i) => (
            <div key={i} className={i > 0 ? "border-t pt-3" : ""}>
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="truncate font-medium text-foreground/90">
                  {m.from || "unknown sender"}
                </span>
                <span className="shrink-0 text-muted-foreground">{formatDateTime(m.date)}</span>
              </div>
              {m.body_html ? (
                <div className="mt-1.5">
                  <EmailBody html={m.body_html} />
                </div>
              ) : (
                <p className="mt-1.5 whitespace-pre-line break-words text-sm text-foreground/80">
                  {m.body || detail.snippet || "(no content)"}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
