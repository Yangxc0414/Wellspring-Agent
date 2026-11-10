import { useState } from "react";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

type Block =
  | { kind: "p"; text: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; lang: string; code: string };

function inline(text: string): ReactNode[] {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${match.index}-b`}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={`${match.index}-c`}>{token.slice(1, -1)}</code>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function parse(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;
  const isSpecial = (line: string) =>
    /^```/.test(line) ||
    /^#{1,3}\s+/.test(line) ||
    /^[-*]\s+/.test(line) ||
    /^\d+\.\s+/.test(line) ||
    /^>\s?/.test(line) ||
    !line.trim();

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({ kind: "code", lang, code: code.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ kind: "quote", text: quote.join(" ") });
      continue;
    }

    const paragraph: string[] = [line];
    index += 1;
    while (index < lines.length && !isSpecial(lines[index])) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push({ kind: "p", text: paragraph.join(" ") });
  }

  return blocks;
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="rich-code">
      <div className="rich-code-head">
        <span>{lang || "code"}</span>
        <button type="button" onClick={copy} aria-label="复制代码">
          <Icon name={copied ? "check" : "copy"} size={11} />
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

export function RichText({ text }: { text: string }) {
  const blocks = parse(text);
  return (
    <div className="rich-text">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return <h4 key={index} data-level={block.level}>{inline(block.text)}</h4>;
        }
        if (block.kind === "ul") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}
            </ul>
          );
        }
        if (block.kind === "ol") {
          return (
            <ol key={index}>
              {block.items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}
            </ol>
          );
        }
        if (block.kind === "quote") {
          return <blockquote key={index}>{inline(block.text)}</blockquote>;
        }
        if (block.kind === "code") {
          return <CodeBlock key={index} code={block.code} lang={block.lang} />;
        }
        return <p key={index}>{inline(block.text)}</p>;
      })}
    </div>
  );
}
