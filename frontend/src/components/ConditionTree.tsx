import { useState } from "react";
import type { RuleCondition } from "../types";
import { describeCondition } from "../ruleFormat";

const KEYWORD_PREVIEW_COUNT = 4;

function KeywordCondition({ c, collapsible }: { c: RuleCondition; collapsible: boolean }) {
  const anyOf = (c.any_of as string[] | undefined) ?? [];
  const fields = (c.fields as string[] | undefined) ?? [];
  const where = fields.map((f) => (f === "snippet" ? "snippet" : f)).join(" or ") || "subject/snippet/body";
  const [expanded, setExpanded] = useState(false);

  const overflow = collapsible && anyOf.length > KEYWORD_PREVIEW_COUNT;
  const shown = overflow && !expanded ? anyOf.slice(0, KEYWORD_PREVIEW_COUNT) : anyOf;

  return (
    <span>
      Contains {shown.map((w, i) => (
        <span key={i}>
          {i > 0 && ", "}
          <span className="rounded bg-foreground/10 px-1 py-0.5">{w}</span>
        </span>
      ))}
      {overflow && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="ml-1 text-muted-foreground underline-offset-2 hover:underline"
        >
          {expanded ? "show less" : `+${anyOf.length - KEYWORD_PREVIEW_COUNT} more`}
        </button>
      )}
      {" "}in the {where}
    </span>
  );
}

export function ConditionTree({
  condition,
  collapsible = false,
  depth = 0,
}: {
  condition: RuleCondition;
  collapsible?: boolean;
  depth?: number;
}) {
  if (condition.type === "group") {
    const nested = (condition.conditions as RuleCondition[] | undefined) ?? [];
    const logic = (condition.logic as string) ?? "AND";

    if (logic === "NOT") {
      return (
        <div className={depth > 0 ? "border-l-2 border-muted-foreground/30 pl-2" : undefined}>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            NOT
          </div>
          {nested[0] && <ConditionTree condition={nested[0]} collapsible={collapsible} depth={depth + 1} />}
        </div>
      );
    }

    return (
      <div className={depth > 0 ? "space-y-1 border-l-2 border-muted-foreground/30 pl-2" : "space-y-1"}>
        {nested.map((n, i) => (
          <div key={i}>
            {i > 0 && (
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {logic}
              </div>
            )}
            <ConditionTree condition={n} collapsible={collapsible} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (condition.type === "keyword") {
    return <KeywordCondition c={condition} collapsible={collapsible} />;
  }

  return <span>{describeCondition(condition)}</span>;
}
