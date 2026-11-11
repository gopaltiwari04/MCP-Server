"use client";

import React from "react";

function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let k = 0;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(
        <strong key={`b-${k++}`} className="font-semibold text-zinc-100">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code
          key={`c-${k++}`}
          className="font-mono text-[11.5px] px-1.5 py-0.5 rounded bg-[#181c26] border border-[#2a3040] text-amber-300"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

function splitPipeRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

function isSeparatorRow(line: string): boolean {
  const cells = splitPipeRow(line);
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}

function isNumericCell(value: string): boolean {
  const cleaned = value.replace(/[$,%+()\s]/g, "");
  return cleaned.length > 0 && /^-?\d+(?:\.\d+)?$/.test(cleaned);
}

export function MarkdownView({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trim();

    if (!line) {
      i++;
      continue;
    }

    // Fenced code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      blocks.push(
        <div key={`code-${key++}`} className="my-2.5 rounded border border-[#232836] bg-[#090b10] overflow-x-auto">
          {lang && (
            <div className="px-3 py-1 border-b border-[#1d222e] text-[10px] font-mono uppercase tracking-wider text-zinc-500">
              {lang}
            </div>
          )}
          <pre className="p-3 text-xs font-mono text-zinc-300 leading-relaxed">{codeLines.join("\n")}</pre>
        </div>
      );
      continue;
    }

    // Markdown table
    if (line.startsWith("|") && i + 1 < lines.length && isSeparatorRow(lines[i + 1])) {
      const headers = splitPipeRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitPipeRow(lines[i]));
        i++;
      }
      blocks.push(
        <div key={`tbl-${key++}`} className="my-3 overflow-x-auto rounded border border-[#232836] bg-[#0b0d12]">
          <table className="w-full text-xs text-left tabular-nums border-collapse">
            <thead>
              <tr className="bg-[#131620] border-b border-[#252a38]">
                {headers.map((h, hIdx) => (
                  <th
                    key={`th-${hIdx}`}
                    className="px-3 py-2 text-[10.5px] font-mono font-semibold uppercase tracking-wider text-zinc-400 whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1a1e29]">
              {rows.map((row, rIdx) => (
                <tr key={`tr-${rIdx}`} className="hover:bg-[#141824]/80 transition-colors">
                  {headers.map((_, cIdx) => {
                    const cell = row[cIdx] ?? "";
                    const numeric = isNumericCell(cell);
                    const positive = /^\+\d/.test(cell.trim()) && cell.includes("%");
                    const negative = /^-\d/.test(cell.trim()) && cell.includes("%");
                    return (
                      <td
                        key={`td-${rIdx}-${cIdx}`}
                        className={`px-3 py-2 whitespace-nowrap ${
                          numeric ? "font-mono text-right" : cIdx === 0 ? "font-mono font-semibold text-zinc-100" : "text-zinc-300"
                        } ${
                          positive
                            ? "text-emerald-400"
                            : negative
                            ? "text-rose-400"
                            : ""
                        }`}
                      >
                        {renderInline(cell)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Headings
    const headingMatch = /^(#{1,4})\s+(.+)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      if (level <= 2) {
        blocks.push(
          <h3
            key={`h-${key++}`}
            className="text-sm font-semibold tracking-tight text-zinc-100 border-b border-[#202532] pb-1.5 mt-3 mb-2 first:mt-0"
          >
            {renderInline(text)}
          </h3>
        );
      } else {
        blocks.push(
          <h4
            key={`h-${key++}`}
            className="text-xs font-mono font-semibold uppercase tracking-wider text-amber-300/90 mt-3 mb-1.5 first:mt-0"
          >
            {renderInline(text)}
          </h4>
        );
      }
      i++;
      continue;
    }

    // Bullet / numbered lists
    if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      const ordered = /^\d+\.\s+/.test(line);
      while (i < lines.length && (/^[-*]\s+/.test(lines[i].trim()) || /^\d+\.\s+/.test(lines[i].trim()))) {
        items.push(lines[i].trim().replace(/^([-*]|\d+\.)\s+/, ""));
        i++;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag
          key={`list-${key++}`}
          className={`my-2 space-y-1 text-[13px] leading-relaxed text-zinc-300 ${
            ordered ? "list-decimal pl-5" : "space-y-1.5"
          }`}
        >
          {items.map((it, idx) => (
            <li key={`li-${idx}`} className={ordered ? "" : "flex items-start gap-2"}>
              {!ordered && <span className="mt-2 h-1 w-1 rounded-full bg-amber-400 shrink-0" />}
              <span>{renderInline(it)}</span>
            </li>
          ))}
        </Tag>
      );
      continue;
    }

    // Blockquote
    if (line.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote
          key={`bq-${key++}`}
          className="my-2 border-l-2 border-amber-500/60 bg-[#12151e] px-3 py-2 text-xs text-zinc-300"
        >
          {renderInline(quoteLines.join(" "))}
        </blockquote>
      );
      continue;
    }

    // Paragraph (collect consecutive text lines)
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].trim().startsWith("#") &&
      !lines[i].trim().startsWith("|") &&
      !lines[i].trim().startsWith("```") &&
      !lines[i].trim().startsWith(">") &&
      !/^[-*]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i].trim());
      i++;
    }
    blocks.push(
      <p key={`p-${key++}`} className="text-[13px] leading-relaxed text-zinc-300 my-1.5">
        {renderInline(paraLines.join(" "))}
      </p>
    );
  }

  return <div className="space-y-0.5">{blocks}</div>;
}
