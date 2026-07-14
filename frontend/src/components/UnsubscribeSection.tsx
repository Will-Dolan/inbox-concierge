import { useEffect, useState } from "react";
import { api } from "../api";
import type { UnsubscribeCandidate } from "../types";
import { MailCheck } from "./icons";
import { Button } from "./ui/button";

type Status = "idle" | "loading" | "done" | "error";

const METHOD_LABEL: Record<UnsubscribeCandidate["method"], string> = {
  one_click: "One-click",
  link: "Manual link",
  mailto: "Email required",
};

interface Props {
  bucketId: string;
  onMarkedRead?: (senderDomain?: string) => void;
}

export function UnsubscribeSection({ bucketId, onMarkedRead }: Props) {
  const [candidates, setCandidates] = useState<UnsubscribeCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [bulkRunning, setBulkRunning] = useState(false);
  const [markingRead, setMarkingRead] = useState(false);
  const [markingSenderRead, setMarkingSenderRead] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLoading(true);
    setStatus({});
    api
      .getUnsubscribeCandidates(bucketId)
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  }, [bucketId]);

  async function runOneClick(c: UnsubscribeCandidate) {
    setStatus((s) => ({ ...s, [c.sender_domain]: "loading" }));
    try {
      await api.executeUnsubscribe(c.url);
      setStatus((s) => ({ ...s, [c.sender_domain]: "done" }));
    } catch {
      setStatus((s) => ({ ...s, [c.sender_domain]: "error" }));
    }
  }

  async function runAllOneClick() {
    setBulkRunning(true);
    for (const c of oneClick.filter((c) => status[c.sender_domain] !== "done")) {
      await runOneClick(c);
    }
    setBulkRunning(false);
  }

  async function markAllRead() {
    setMarkingRead(true);
    try {
      await api.markThreadsRead(bucketId);
      onMarkedRead?.();
    } finally {
      setMarkingRead(false);
    }
  }

  async function markSenderRead(senderDomain: string) {
    setMarkingSenderRead((prev) => ({ ...prev, [senderDomain]: true }));
    try {
      await api.markThreadsRead(bucketId, senderDomain);
      onMarkedRead?.(senderDomain);
    } finally {
      setMarkingSenderRead((prev) => ({ ...prev, [senderDomain]: false }));
    }
  }

  if (loading) {
    return (
      <div>
        <UnsubscribeActions markingRead={markingRead} onMarkAllRead={markAllRead} />
        <p className="text-xs text-muted-foreground">Checking for unsubscribe links…</p>
      </div>
    );
  }
  if (candidates.length === 0) {
    return (
      <div>
        <UnsubscribeActions markingRead={markingRead} onMarkAllRead={markAllRead} />
        <p className="text-xs text-muted-foreground">
          No senders in this bucket have a List-Unsubscribe email header.
        </p>
      </div>
    );
  }

  const oneClick = candidates.filter((c) => c.method === "one_click");
  const manual = candidates.filter((c) => c.method !== "one_click");

  return (
    <div>
      <UnsubscribeActions markingRead={markingRead} onMarkAllRead={markAllRead} />
      <p className="mb-2 text-[11px] text-muted-foreground">
        Senders in this bucket with a List-Unsubscribe email header, grouped by domain.
      </p>

      {oneClick.length > 0 && (
        <div className="mb-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Automatable ({oneClick.length})
            </span>
            <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" onClick={runAllOneClick} disabled={bulkRunning}>
              {bulkRunning ? "Working…" : "Unsubscribe from all"}
            </Button>
          </div>
          <ul className="space-y-1">
            {oneClick.map((c) => (
              <Row
                key={c.sender_domain}
                c={c}
                status={status[c.sender_domain] ?? "idle"}
                markingRead={markingSenderRead[c.sender_domain] ?? false}
                onRun={() => runOneClick(c)}
                onMarkRead={() => markSenderRead(c.sender_domain)}
              />
            ))}
          </ul>
        </div>
      )}

      {manual.length > 0 && (
        <div>
          <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Needs your click ({manual.length})
          </span>
          <ul className="mt-1.5 space-y-1">
            {manual.map((c) => (
              <Row
                key={c.sender_domain}
                c={c}
                status="idle"
                markingRead={markingSenderRead[c.sender_domain] ?? false}
                onRun={() => {}}
                onMarkRead={() => markSenderRead(c.sender_domain)}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function UnsubscribeActions({
  markingRead,
  onMarkAllRead,
}: {
  markingRead: boolean;
  onMarkAllRead: () => void;
}) {
  return (
    <div className="mb-2 flex justify-end">
      <Button
        size="sm"
        variant="secondary"
        className="h-6 gap-1.5 px-2 text-[11px]"
        onClick={onMarkAllRead}
        disabled={markingRead}
      >
        <MailCheck className="h-3 w-3" />
        {markingRead ? "Marking…" : "Mark all as read"}
      </Button>
    </div>
  );
}

function Row({
  c,
  status,
  markingRead,
  onRun,
  onMarkRead,
}: {
  c: UnsubscribeCandidate;
  status: Status;
  markingRead: boolean;
  onRun: () => void;
  onMarkRead: () => void;
}) {
  return (
    <li className="flex items-center justify-between gap-2 rounded-md bg-muted/50 px-2 py-1.5">
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-foreground">{c.sender_domain}</p>
        <p className="text-[10px] text-muted-foreground">
          {c.thread_count} thread{c.thread_count === 1 ? "" : "s"} · {METHOD_LABEL[c.method]}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          size="sm"
          variant="secondary"
          className="h-6 gap-1 px-2 text-[11px]"
          onClick={onMarkRead}
          disabled={markingRead}
        >
          <MailCheck className="h-3 w-3" />
          {markingRead ? "Marking…" : "Mark read"}
        </Button>
        {c.method === "one_click" ? (
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-[11px]"
            onClick={onRun}
            disabled={status === "loading" || status === "done"}
          >
            {status === "loading" ? "…" : status === "done" ? "Done" : status === "error" ? "Retry" : "Unsubscribe"}
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" asChild>
            <a href={c.url} target="_blank" rel="noreferrer">
              {c.method === "mailto" ? "Email" : "Open link"}
            </a>
          </Button>
        )}
      </div>
    </li>
  );
}
