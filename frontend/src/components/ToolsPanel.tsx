import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import type { Bucket, UpdateBucketResult } from "../types";
import { Menu } from "./icons";
import { DigestSection } from "./DigestSection";
import { UnsubscribeSection } from "./UnsubscribeSection";
import { RuleSection } from "./RuleSection";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "./ui/accordion";

interface Props {
  bucket: Bucket;
  onRuleSaved: (result?: UpdateBucketResult) => void;
  onMarkedRead: (senderDomain?: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSections?: string[];
}

const MIN_WIDTH = 260;
const MAX_WIDTH = 640;
const DEFAULT_WIDTH = 320;
const WIDTH_STORAGE_KEY = "tools-panel-width";

export function ToolsPanel({
  bucket,
  onRuleSaved,
  onMarkedRead,
  open,
  onOpenChange,
  defaultSections = ["rules"],
}: Props) {
  const [collapsed, setCollapsed] = useState(!open);
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem(WIDTH_STORAGE_KEY));
    return saved >= MIN_WIDTH && saved <= MAX_WIDTH ? saved : DEFAULT_WIDTH;
  });
  const [resizing, setResizing] = useState(false);
  const resizeStart = useRef<{ x: number; width: number } | null>(null);

  const onPointerMove = useCallback((e: PointerEvent) => {
    if (!resizeStart.current) return;
    const delta = resizeStart.current.x - e.clientX;
    const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, resizeStart.current.width + delta));
    setWidth(next);
  }, []);

  const onPointerUp = useCallback(() => {
    resizeStart.current = null;
    setResizing(false);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
  }, [onPointerMove]);

  useEffect(() => {
    if (!resizing) return;
    localStorage.setItem(WIDTH_STORAGE_KEY, String(width));
  }, [width, resizing]);

  useEffect(() => {
    setCollapsed(!open);
  }, [open]);

  function startResize(e: React.PointerEvent) {
    resizeStart.current = { x: e.clientX, width };
    setResizing(true);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }

  return (
    <div className="flex h-full shrink-0">
      <div className="flex h-full w-8 shrink-0 flex-col items-center gap-3 border-l bg-background py-3">
        <button
          type="button"
          onClick={() => onOpenChange(collapsed)}
          className="text-muted-foreground transition hover:text-foreground"
          title={collapsed ? "Show tools" : "Hide tools"}
        >
          <Menu className="h-4 w-4" />
        </button>
        <span className="text-[10px] font-medium tracking-wide text-muted-foreground [writing-mode:vertical-rl]">
          TOOLS
        </span>
      </div>

      <div
        className={clsx(
          "relative h-full overflow-hidden border-l bg-background",
          !resizing && "transition-[width] duration-200 ease-in-out",
        )}
        style={{ width: collapsed ? 0 : width }}
      >
        {!collapsed && (
          <div
            onPointerDown={startResize}
            className={clsx(
              "absolute left-0 top-0 z-10 h-full w-1.5 -translate-x-1/2 cursor-col-resize touch-none select-none",
              resizing ? "bg-primary/40" : "hover:bg-primary/20",
            )}
          />
        )}

        <div className="flex h-full flex-col" style={{ width }}>
          <div className="border-b px-4 py-3">
            <span className="text-sm font-semibold text-foreground">Tools</span>
            <span className="ml-1.5 text-xs text-muted-foreground">for "{bucket.name}"</span>
          </div>

          <div className="flex-1 overflow-y-auto px-4">
            <Accordion type="multiple" defaultValue={defaultSections}>
              <AccordionItem value="digest">
                <AccordionTrigger className="text-sm">Digest</AccordionTrigger>
                <AccordionContent>
                  <DigestSection bucketId={bucket.id} />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="unsubscribe">
                <AccordionTrigger className="text-sm">Unsubscribe</AccordionTrigger>
                <AccordionContent>
                  <UnsubscribeSection bucketId={bucket.id} onMarkedRead={onMarkedRead} />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="rules" className="border-b-0">
                <AccordionTrigger className="text-sm">Rules</AccordionTrigger>
                <AccordionContent>
                  <RuleSection bucket={bucket} onSaved={onRuleSaved} />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </div>
      </div>
    </div>
  );
}
