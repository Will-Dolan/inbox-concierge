import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, pollJob } from "../api";
import type { Bucket, SyncResult, Thread, ThreadDetail, UpdateBucketResult } from "../types";
import { BucketBar } from "./BucketBar";
import { BucketEditorDialog } from "./BucketEditorDialog";
import { ThreadRow } from "./ThreadRow";
import { ThreadDetailPanel } from "./ThreadDetailPanel";
import { ToolsPanel } from "./ToolsPanel";
import { LogOut, MailCheck, Refresh } from "./icons";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";

const AUTO_SYNC_INTERVAL_MS = 2 * 60 * 1000;

type SortMode = "time" | "unread";

interface Props {
  userEmail: string;
  onLogout: () => void;
}

export function InboxView({ userEmail, onLogout }: Props) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [activeBucket, setActiveBucket] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [bucketPendingDelete, setBucketPendingDelete] = useState<Bucket | null>(null);
  const [judgingBucketIds, setJudgingBucketIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [expandedDetails, setExpandedDetails] = useState<Map<string, ThreadDetail>>(new Map());
  const [expandedLoadingIds, setExpandedLoadingIds] = useState<Set<string>>(new Set());
  const [sortMode, setSortMode] = useState<SortMode>("time");
  const [markingRead, setMarkingRead] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const activeBucketRef = useRef<string | null>(null);
  const threadRequestSeq = useRef(0);
  activeBucketRef.current = activeBucket;

  async function handleToggleThread(thread: Thread) {
    if (expandedIds.has(thread.id)) {
      setExpandedIds((prev) => {
        const next = new Set(prev);
        next.delete(thread.id);
        return next;
      });
      setExpandedDetails((prev) => {
        const next = new Map(prev);
        next.delete(thread.id);
        return next;
      });
      return;
    }
    setExpandedIds((prev) => new Set(prev).add(thread.id));
    setExpandedLoadingIds((prev) => new Set(prev).add(thread.id));
    try {
      const detail = await api.getThread(thread.id);
      setExpandedDetails((prev) => new Map(prev).set(thread.id, detail));
      if (!detail.unread) {
        setThreads((prev) => prev.map((t) => (t.id === thread.id ? { ...t, unread: false } : t)));
      }
    } finally {
      setExpandedLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(thread.id);
        return next;
      });
    }
  }

  const loadThreads = useCallback(async (bucket: string | null) => {
    const requestId = ++threadRequestSeq.current;
    const data = await api.listThreads(bucket ?? undefined);
    if (requestId === threadRequestSeq.current && activeBucketRef.current === bucket) {
      setThreads(data);
    }
  }, []);

  const loadBuckets = useCallback(async () => {
    const data = await api.listBuckets();
    setBuckets(data);
  }, []);

  const handleSync = useCallback(async (opts: { silent?: boolean } = {}) => {
    setSyncing(true);
    if (!opts.silent) setStatus("Syncing your last 200 threads…");
    try {
      const { job_id } = await api.startSync();
      const final = await pollJob<SyncResult>(job_id, { intervalMs: 2000 });
      if (final.status === "done" && final.result) {
        setLastSyncedAt(new Date());
        if (!opts.silent) {
          setStatus(
            `Synced ${final.result.threads_synced} threads, classified ${final.result.threads_classified}.`,
          );
        }
      } else if (!opts.silent) {
        setStatus(final.error ?? "Sync failed.");
      }
      await Promise.all([loadBuckets(), loadThreads(activeBucketRef.current)]);
    } finally {
      setSyncing(false);
      if (!opts.silent) setTimeout(() => setStatus(null), 4000);
    }
  }, [loadBuckets, loadThreads]);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadBuckets(), loadThreads(null)]).finally(() => setLoading(false));
  }, [loadBuckets, loadThreads]);

  // Keep the inbox fresh without the user having to think about it: sync once
  // on load, then quietly in the background on an interval. The manual button
  // stays as a "do it now" override (each sync costs Gmail + LLM calls, so we
  // don't poll aggressively).
  useEffect(() => {
    handleSync({ silent: true });
    const id = setInterval(() => handleSync({ silent: true }), AUTO_SYNC_INTERVAL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadThreads(activeBucket);
  }, [activeBucket, loadThreads]);

  const bucketsByName = useMemo(() => new Map(buckets.map((b) => [b.name, b])), [buckets]);
  const activeBucketObj = activeBucket ? bucketsByName.get(activeBucket) : null;
  const unreadCount = threads.filter((thread) => thread.unread).length;

  // Threads already arrive sorted by time (desc) from the API; for "unread"
  // mode we just stable-sort unread threads to the front of that order.
  const sortedThreads = useMemo(() => {
    if (sortMode === "time") return threads;
    return [...threads].sort((a, b) => Number(b.unread) - Number(a.unread));
  }, [threads, sortMode]);

  async function confirmDeleteBucket() {
    const bucket = bucketPendingDelete;
    if (!bucket) return;
    setBucketPendingDelete(null);
    if (activeBucket === bucket.name) setActiveBucket(null);
    await api.deleteBucket(bucket.id);
    await Promise.all([loadBuckets(), loadThreads(activeBucket === bucket.name ? null : activeBucket)]);
  }

  function handleBucketSaved(result?: UpdateBucketResult) {
    void Promise.all([loadBuckets(), loadThreads(activeBucketRef.current)]);

    if (!result?.classification_job_id) return;

    setJudgingBucketIds((prev) => new Set(prev).add(result.id));
    setStatus("AI judgment is reclassifying this bucket…");
    void pollJob(result.classification_job_id, { intervalMs: 1200 }).then((final) => {
      setJudgingBucketIds((prev) => {
        const next = new Set(prev);
        next.delete(result.id);
        return next;
      });
      if (final.status === "failed") {
        setStatus(final.error ?? "AI judgment failed.");
        setTimeout(() => setStatus(null), 4000);
      } else {
        setStatus(null);
      }
      return Promise.all([loadBuckets(), loadThreads(activeBucketRef.current)]);
    });
  }

  async function handleCorrect(thread: Thread, bucketName: string, action: "add" | "remove") {
    const bucket = bucketsByName.get(bucketName);
    if (!bucket) return;

    // optimistic update
    setThreads((prev) =>
      prev.map((t) =>
        t.id === thread.id
          ? {
              ...t,
              tags:
                action === "add"
                  ? [...t.tags, bucketName]
                  : t.tags.filter((tag) => tag !== bucketName),
            }
          : t,
      ),
    );

    await api.addCorrection(thread.id, bucket.id, action);
  }

  async function handleMarkAllRead() {
    if (activeBucket && !activeBucketObj) return;
    setMarkingRead(true);
    try {
      const result = await api.markThreadsRead(activeBucketObj?.id);
      setThreads((prev) => prev.map((thread) => ({ ...thread, unread: false })));
      setExpandedDetails((prev) => {
        const next = new Map(prev);
        for (const [id, detail] of next) {
          next.set(id, { ...detail, unread: false });
        }
        return next;
      });
      setStatus(
        result.failed > 0
          ? `Marked ${result.marked} thread${result.marked === 1 ? "" : "s"} read; ${result.failed} failed.`
          : `Marked ${result.marked} thread${result.marked === 1 ? "" : "s"} read.`,
      );
      if (result.failed > 0) await loadThreads(activeBucketRef.current);
      setTimeout(() => setStatus(null), 3000);
    } catch {
      setStatus("Couldn't mark threads read.");
      setTimeout(() => setStatus(null), 3000);
    } finally {
      setMarkingRead(false);
    }
  }

  return (
    <TooltipProvider>
      <div className="flex h-screen flex-col bg-background">
        <header className="flex shrink-0 items-center justify-between border-b bg-background px-5 py-3">
          <span className="text-sm font-semibold text-foreground">Inbox Concierge</span>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">{userEmail}</span>
            <Tooltip delayDuration={300}>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" onClick={() => handleSync()} disabled={syncing}>
                  <Refresh className={syncing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
                  {syncing ? "Syncing…" : "Sync now"}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={6} className="max-w-xs">
                Inbox Concierge syncs automatically every 2 minutes. This fetches new mail
                and re-classifies it right away instead of waiting.
                {lastSyncedAt && (
                  <div className="mt-0.5 text-primary-foreground/70">
                    Last synced {lastSyncedAt.toLocaleTimeString()}
                  </div>
                )}
              </TooltipContent>
            </Tooltip>
            <Tooltip delayDuration={300}>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="sm" onClick={onLogout}>
                  <LogOut className="h-3.5 w-3.5" />
				  Log Out
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={6}>
                Log out
              </TooltipContent>
            </Tooltip>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <BucketBar
            buckets={buckets}
            active={activeBucket}
            onSelect={setActiveBucket}
            onNewBucket={() => setDialogOpen(true)}
            onDeleteBucket={setBucketPendingDelete}
            judgingBucketIds={judgingBucketIds}
          />

          <div className="flex min-w-0 flex-1 flex-col">
            {status && (
              <div className="border-b bg-accent px-5 py-2 text-xs text-accent-foreground">
                {status}
              </div>
            )}

            <div className="flex shrink-0 items-center justify-between gap-2 border-b px-4 py-2">
              <h1 className="text-sm font-semibold text-foreground">
                {activeBucket ?? "Inbox"}
              </h1>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  className="h-7 gap-1.5 text-xs"
                  onClick={handleMarkAllRead}
                  disabled={markingRead || unreadCount === 0 || (activeBucket !== null && !activeBucketObj)}
                >
                  <MailCheck className="h-3.5 w-3.5" />
                  {markingRead ? "Marking…" : "Mark all as read"}
                </Button>
                <span className="text-xs text-muted-foreground">Sort by</span>
                <Select value={sortMode} onValueChange={(v) => setSortMode(v as SortMode)}>
                  <SelectTrigger className="h-7 w-32 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="time">Time</SelectItem>
                    <SelectItem value="unread">Unread first</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <main className="flex-1 overflow-y-auto p-4">
              {loading ? (
                <div className="p-8 text-center text-sm text-muted-foreground">Loading…</div>
              ) : threads.length === 0 ? (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No threads {activeBucket ? `in "${activeBucket}"` : "yet"}. Try syncing.
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {sortedThreads.map((t) => (
                    <div key={t.id}>
                      <ThreadRow
                        thread={t}
                        bucketsByName={bucketsByName}
                        activeBucketName={activeBucket}
                        expanded={expandedIds.has(t.id)}
                        onToggle={handleToggleThread}
                        onCorrect={handleCorrect}
                      />
                      {expandedIds.has(t.id) && (
                        <ThreadDetailPanel
                          detail={expandedDetails.get(t.id) ?? null}
                          loading={expandedLoadingIds.has(t.id)}
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </main>
          </div>

          {activeBucketObj && (
            <ToolsPanel
              bucket={activeBucketObj}
              open={toolsOpen}
              onOpenChange={setToolsOpen}
              onRuleSaved={handleBucketSaved}
              onMarkedRead={(senderDomain) => {
                setThreads((prev) =>
                  prev.map((thread) =>
                    senderDomain && thread.sender_domain !== senderDomain
                      ? thread
                      : { ...thread, unread: false },
                  ),
                );
                setExpandedDetails((prev) => {
                  const next = new Map(prev);
                  for (const [id, detail] of next) {
                    if (!senderDomain || detail.sender_domain === senderDomain) {
                      next.set(id, { ...detail, unread: false });
                    }
                  }
                  return next;
                });
                void loadThreads(activeBucketRef.current);
              }}
            />
          )}
        </div>
      </div>

      <BucketEditorDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={() => {
          loadBuckets();
          loadThreads(activeBucket);
        }}
      />

      <AlertDialog
        open={bucketPendingDelete != null}
        onOpenChange={(open) => {
          if (!open) setBucketPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{bucketPendingDelete?.name}"?</AlertDialogTitle>
            <AlertDialogDescription>
              Its tags will be removed from threads. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDeleteBucket}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </TooltipProvider>
  );
}
