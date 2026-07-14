import clsx from "clsx";
import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Refresh, X } from "./icons";
import type { Bucket } from "../types";
import { ConditionTree } from "./ConditionTree";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { Button } from "./ui/button";

interface Props {
  buckets: Bucket[];
  active: string | null;
  onSelect: (name: string | null) => void;
  onNewBucket: () => void;
  onDeleteBucket: (bucket: Bucket) => void;
  judgingBucketIds?: Set<string>;
}

export function BucketBar({
  buckets,
  active,
  onSelect,
  onNewBucket,
  onDeleteBucket,
  judgingBucketIds = new Set(),
}: Props) {
  const [defaultsOpen, setDefaultsOpen] = useState(true);
  const defaultBuckets = buckets.filter((b) => b.kind === "system");
  const customBuckets = buckets.filter((b) => b.kind !== "system");
  const activeInDefaults = defaultBuckets.some((b) => b.name === active);

  return (
    <nav className="flex h-full w-56 shrink-0 flex-col gap-1 overflow-y-auto border-r bg-background px-3 py-4">
      <h2 className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Buckets
      </h2>
      <Item label="Mailbox" active={active === null} onClick={() => onSelect(null)} />
      {defaultBuckets.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setDefaultsOpen((v) => !v)}
            className={clsx(
              "flex w-full items-center gap-1.5 rounded-lg px-3 py-2 text-left text-sm font-medium transition",
              activeInDefaults && !defaultsOpen
                ? "bg-primary/10 text-foreground/80"
                : "text-foreground/80 hover:bg-muted",
            )}
          >
            {defaultsOpen ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
            <span className="truncate">Defaults</span>
          </button>
          {defaultsOpen && (
            <div className="ml-3 flex flex-col gap-1 border-l pl-2">
              {defaultBuckets.map((b) => (
                <BucketItem
                  key={b.id}
                  bucket={b}
                  active={active}
                  onSelect={onSelect}
                  onDeleteBucket={onDeleteBucket}
                  judging={judgingBucketIds.has(b.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
      {customBuckets.map((b) => (
        <BucketItem
          key={b.id}
          bucket={b}
          active={active}
          onSelect={onSelect}
          onDeleteBucket={onDeleteBucket}
          judging={judgingBucketIds.has(b.id)}
        />
      ))}
      <Button
        type="button"
        variant="outline"
        onClick={onNewBucket}
        className="mt-1 gap-1.5 border-dashed text-muted-foreground"
      >
        <Plus className="h-3 w-3" />
        New bucket
      </Button>
    </nav>
  );
}

function BucketItem({
  bucket: b,
  active,
  onSelect,
  onDeleteBucket,
  judging = false,
}: {
  bucket: Bucket;
  active: string | null;
  onSelect: (name: string | null) => void;
  onDeleteBucket: (bucket: Bucket) => void;
  judging?: boolean;
}) {
  return (
    <Tooltip delayDuration={300}>
      <TooltipTrigger asChild>
        <span>
          <Item
            label={b.name}
            active={active === b.name}
            onClick={() => onSelect(b.name)}
            pending={judging || (b.mode === "semantic" && b.mode_source === "agent" && !b.rule_version)}
            deletable={b.kind === "custom"}
            onDelete={() => onDeleteBucket(b)}
          />
        </span>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8} className="max-w-sm">
        <div className="font-medium">{b.mode === "deterministic" ? "Rule-based" : "AI-judged"}</div>
        {b.description && <div className="mt-0.5 text-primary-foreground/70">{b.description}</div>}
        {b.rule_conditions && b.rule_conditions.length > 0 && (
          <div className="mt-1.5 space-y-1 border-t border-primary-foreground/20 pt-1.5">
            <div className="text-[10px] uppercase tracking-wide text-primary-foreground/60">
              {b.rule_logic === "OR" ? "Matches any of" : b.rule_logic === "NOT" ? "Does not match" : "Matches all of"}
            </div>
            {b.rule_conditions.map((c, i) => (
              <div key={i} className="text-primary-foreground/80">
                <ConditionTree condition={c} />
              </div>
            ))}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

function Item({
  label,
  active,
  onClick,
  pending,
  deletable,
  onDelete,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  pending?: boolean;
  deletable?: boolean;
  onDelete?: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick();
      }}
      className={clsx(
        "group flex w-full cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-left text-sm font-medium transition",
        active ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-muted",
      )}
    >
      <span className="truncate">{label}</span>
      <span className="flex shrink-0 items-center gap-1">
        {pending && (
          <Refresh
            className={clsx(
              "h-3 w-3 animate-spin",
              active ? "text-primary-foreground/80" : "text-primary",
            )}
          />
        )}
        {deletable && (
          <button
            type="button"
            aria-label={`Delete ${label}`}
            onClick={(e) => {
              e.stopPropagation();
              onDelete?.();
            }}
            className={clsx(
              "rounded p-0.5 opacity-0 transition group-hover:opacity-100",
              active ? "text-primary-foreground/60 hover:text-primary-foreground" : "text-muted-foreground hover:text-destructive",
            )}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </span>
    </div>
  );
}
