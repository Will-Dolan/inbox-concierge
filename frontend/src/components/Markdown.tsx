// Minimal, dependency-free markdown renderer for short LLM-generated text
// (digests, rationale). Renders directly to React elements - no
// dangerouslySetInnerHTML, so there's no HTML-injection surface to sanitize.
// Supports paragraphs, "-"/"*" bullet lists, **bold**, *italics*, `code`.

import { Fragment } from "react";

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1] !== undefined) {
      nodes.push(<strong key={`${keyPrefix}-${i}`}>{match[1]}</strong>);
    } else if (match[2] !== undefined) {
      nodes.push(<em key={`${keyPrefix}-${i}`}>{match[2]}</em>);
    } else if (match[3] !== undefined) {
      nodes.push(
        <code key={`${keyPrefix}-${i}`} className="rounded bg-muted px-1 py-0.5 text-[0.9em]">
          {match[3]}
        </code>,
      );
    }
    last = re.lastIndex;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

interface Props {
  text: string;
}

export function Markdown({ text }: Props) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push(<p key={blocks.length}>{renderInline(paragraph.join(" "), `p${blocks.length}`)}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (list.length === 0) return;
    blocks.push(
      <ul key={blocks.length} className="list-disc space-y-0.5 pl-4">
        {list.map((item, i) => (
          <li key={i}>{renderInline(item, `l${blocks.length}-${i}`)}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const bulletMatch = /^[-*]\s+(.*)$/.exec(line);
    const headingStripped = line.replace(/^#+\s*/, "");

    if (!line) {
      flushParagraph();
      flushList();
    } else if (bulletMatch) {
      flushParagraph();
      list.push(bulletMatch[1]);
    } else {
      flushList();
      paragraph.push(headingStripped);
    }
  }
  flushParagraph();
  flushList();

  return <Fragment>{blocks}</Fragment>;
}
