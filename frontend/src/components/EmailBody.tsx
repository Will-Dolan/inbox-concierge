import { useRef, useState } from "react";

const IFRAME_STYLE = `
  body { margin: 0; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1a1a1a; word-wrap: break-word; overflow-wrap: anywhere; }
  img { max-width: 100%; height: auto; }
  a { color: #2563eb; }
  table { max-width: 100%; }
`;

interface Props {
  html: string;
}

// Emails are just MIME - the text/html part is what Gmail itself renders. We
// sanitize it server-side (see gmail/body.py) and then render the real HTML
// here, sandboxed, instead of flattening it to plain text.
export function EmailBody({ html }: Props) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(80);

  function handleLoad() {
    const doc = ref.current?.contentDocument;
    if (doc?.body) {
      setHeight(doc.body.scrollHeight + 4);
    }
  }

  const srcDoc = `<!doctype html><html><head><style>${IFRAME_STYLE}</style></head><body>${html}</body></html>`;

  return (
    <iframe
      ref={ref}
      title="Email content"
      srcDoc={srcDoc}
      onLoad={handleLoad}
      sandbox="allow-same-origin allow-popups"
      style={{ height }}
      className="w-full border-0"
    />
  );
}
