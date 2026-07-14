import type { ConditionType, RuleCondition } from "./types";

export const CONDITION_TYPE_LABELS: Record<ConditionType, string> = {
  keyword: "Keyword",
  sender: "Sender",
  gmail_label: "Gmail label",
  header_present: "Header present",
  time_range: "Time range",
  extracted_field: "Extracted field",
  recipient_count: "Recipient count",
  is_reply: "Is a reply",
  has_attachment: "Has attachment",
  group: "Group",
};

const FIELD_LABELS: Record<string, string> = {
  subject: "subject",
  snippet: "snippet",
  body: "body",
  domain: "domain",
  email: "email address",
  list_id: "mailing list",
};

function humanize(key: string): string {
  return key.replace(/_/g, " ");
}

export function describeCondition(c: RuleCondition): string {
  switch (c.type) {
    case "keyword": {
      const anyOf = (c.any_of as string[] | undefined) ?? [];
      const fields = (c.fields as string[] | undefined) ?? [];
      const where = fields.map((f) => FIELD_LABELS[f] ?? f).join(" or ");
      return `Contains "${anyOf.join('", "')}" in the ${where || "subject/snippet/body"}`;
    }
    case "sender": {
      const parts = (["domain", "email", "list_id"] as const)
        .filter((k) => c[k])
        .map((k) => `${FIELD_LABELS[k]} is ${c[k]}`);
      return `Sender ${parts.join(" and ")}`;
    }
    case "gmail_label":
      return `Has Gmail label "${c.label}"`;
    case "header_present":
      return `Has header "${c.header}"`;
    case "time_range":
      return `Received between ${c.start || "any time"} and ${c.end || "any time"}`;
    case "extracted_field":
      return `${humanize(String(c.field))} ${c.op} ${c.value}`;
    case "recipient_count":
      return `Recipient count ${c.op} ${c.value}`;
    case "is_reply":
      return c.value === false ? "Is not a reply" : "Is a reply";
    case "has_attachment":
      return c.value === false ? "Has no attachment" : "Has an attachment";
    case "group": {
      const nested = (c.conditions as RuleCondition[] | undefined) ?? [];
      const logic = (c.logic as string) ?? "AND";
      const parts = nested.map(describeCondition);
      if (logic === "NOT") return `NOT (${parts[0] ?? ""})`;
      const joiner = logic === "OR" ? " OR " : " AND ";
      return parts.length > 1 ? `(${parts.join(joiner)})` : parts[0] ?? "";
    }
    default:
      return JSON.stringify(c);
  }
}

export function emptyConditionFor(type: RuleCondition["type"]): RuleCondition {
  switch (type) {
    case "keyword":
      return { type, any_of: [], fields: ["subject", "snippet", "body"] };
    case "sender":
      return { type, domain: "" };
    case "gmail_label":
      return { type, label: "" };
    case "header_present":
      return { type, header: "" };
    case "time_range":
      return { type, start: "", end: "" };
    case "extracted_field":
      return { type, field: "", op: "==", value: "" };
    case "recipient_count":
      return { type, op: ">=", value: 1 };
    case "is_reply":
      return { type, value: true };
    case "has_attachment":
      return { type, value: true };
    case "group":
      return { type, logic: "AND", conditions: [] };
  }
}
