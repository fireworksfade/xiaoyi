import { useMemo, type ReactNode } from 'react';

/**
 * 助手回答的轻量 Markdown 渲染：标题、段落、加粗/斜体/删除线、行内代码、代码块、
 * 有序/无序列表（可嵌套）、引用、分隔线、GFM 表格和 http(s) 链接。
 *
 * 只生成 React 元素，不解析原始 HTML（不用 dangerouslySetInnerHTML），
 * 工具输出和日志里的不可信文本因此只会按文本显示。流式输出中未闭合的标记按原文显示。
 */

type Align = 'left' | 'center' | 'right' | null;

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; lines: string[] }
  | { type: 'code'; text: string }
  | { type: 'hr' }
  | { type: 'quote'; children: Block[] }
  | { type: 'list'; ordered: boolean; start: number; items: Block[][] }
  | { type: 'table'; align: Align[]; header: string[]; rows: string[][] };

const FENCE = /^\s{0,3}(`{3,}|~{3,})/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
const HR = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const QUOTE = /^\s{0,3}>\s?/;
const LIST_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])(\s+)(.*)$/;
const TABLE_DIVIDER = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

function indentOf(line: string) {
  return line.length - line.trimStart().length;
}

function isBlank(line: string) {
  return line.trim() === '';
}

/** 按未转义、不在行内代码里的 | 切分表格行。 */
function splitRow(line: string): string[] {
  let text = line.trim();
  if (text.startsWith('|')) text = text.slice(1);
  if (text.endsWith('|') && !text.endsWith('\\|')) text = text.slice(0, -1);
  const cells: string[] = [];
  let current = '';
  let inCode = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '\\' && text[i + 1] === '|') {
      current += '|';
      i += 1;
    } else if (char === '`') {
      inCode = !inCode;
      current += char;
    } else if (char === '|' && !inCode) {
      cells.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function isTableStart(lines: string[], index: number) {
  const next = lines[index + 1];
  return (
    lines[index].includes('|') &&
    next !== undefined &&
    next.includes('-') &&
    TABLE_DIVIDER.test(next)
  );
}

function startsBlock(lines: string[], index: number) {
  const line = lines[index];
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    HR.test(line) ||
    QUOTE.test(line) ||
    LIST_ITEM.test(line) ||
    isTableStart(lines, index)
  );
}

function parseList(lines: string[], start: number) {
  const first = LIST_ITEM.exec(lines[start])!;
  const baseIndent = first[1].length;
  const ordered = /\d/.test(first[2]);
  const items: string[][] = [];
  let contentIndent = 0;
  let i = start;

  while (i < lines.length) {
    const line = lines[i];
    const marker = LIST_ITEM.exec(line);
    if (
      marker &&
      marker[1].length <= baseIndent + 1 &&
      /\d/.test(marker[2]) === ordered
    ) {
      contentIndent = marker[1].length + marker[2].length + marker[3].length;
      items.push([marker[4]]);
      i += 1;
      continue;
    }
    if (marker && marker[1].length <= baseIndent + 1) break; // 换了列表类型
    if (isBlank(line)) {
      let next = i + 1;
      while (next < lines.length && isBlank(lines[next])) next += 1;
      const following = lines[next];
      const continues =
        following !== undefined &&
        (indentOf(following) >= Math.min(contentIndent, baseIndent + 2) ||
          (LIST_ITEM.exec(following)?.[1].length ?? Infinity) <=
            baseIndent + 1);
      if (!continues) break;
      items[items.length - 1].push('');
      i += 1;
      continue;
    }
    if (indentOf(line) >= Math.min(contentIndent, baseIndent + 2)) {
      items[items.length - 1].push(
        line.slice(Math.min(indentOf(line), contentIndent)),
      );
      i += 1;
      continue;
    }
    const previous = items[items.length - 1];
    if (!isBlank(previous[previous.length - 1]) && !startsBlock(lines, i)) {
      previous.push(line.trim()); // 段落的惰性续行
      i += 1;
      continue;
    }
    break;
  }

  return {
    block: {
      type: 'list' as const,
      ordered,
      start: ordered ? Number.parseInt(first[2], 10) : 1,
      items: items.map((item) => parseBlocks(item)),
    },
    next: i,
  };
}

export function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (isBlank(line)) {
      i += 1;
      continue;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过结束围栏（流式输出时可能还没到）
      blocks.push({ type: 'code', text: body.join('\n') });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        text: heading[2],
      });
      i += 1;
      continue;
    }

    if (HR.test(line)) {
      blocks.push({ type: 'hr' });
      i += 1;
      continue;
    }

    if (isTableStart(lines, i)) {
      const header = splitRow(line);
      const align = splitRow(lines[i + 1]).map((cell): Align => {
        const left = cell.startsWith(':');
        const right = cell.endsWith(':');
        return left && right
          ? 'center'
          : right
            ? 'right'
            : left
              ? 'left'
              : null;
      });
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && !isBlank(lines[i]) && lines[i].includes('|')) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ type: 'table', align, header, rows });
      continue;
    }

    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i])) {
        body.push(lines[i].replace(QUOTE, ''));
        i += 1;
      }
      blocks.push({ type: 'quote', children: parseBlocks(body) });
      continue;
    }

    if (LIST_ITEM.test(line)) {
      const { block, next } = parseList(lines, i);
      blocks.push(block);
      i = next;
      continue;
    }

    const paragraph = [line.trim()];
    i += 1;
    while (i < lines.length && !isBlank(lines[i]) && !startsBlock(lines, i)) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: 'paragraph', lines: paragraph });
  }
  return blocks;
}

const ESCAPABLE = new Set('\\`*_{}[]()#+-.!|~>'.split(''));

function findClosing(text: string, marker: string, from: number) {
  let index = text.indexOf(marker, from);
  while (index !== -1) {
    // 结束标记前不能是空白，避免把 “OPS_* 与 e2e-*” 里的星号当成强调
    if (index > from && !/\s/.test(text[index - 1])) return index;
    index = text.indexOf(marker, index + 1);
  }
  return -1;
}

function renderInline(text: string, keyPrefix = 'i'): ReactNode[] {
  const nodes: ReactNode[] = [];
  let buffer = '';
  let i = 0;
  const flush = () => {
    if (buffer) nodes.push(buffer);
    buffer = '';
  };
  const key = () => `${keyPrefix}-${nodes.length}`;

  while (i < text.length) {
    const char = text[i];

    if (char === '\\' && ESCAPABLE.has(text[i + 1] ?? '')) {
      buffer += text[i + 1];
      i += 2;
      continue;
    }

    if (char === '`') {
      let ticks = 1;
      while (text[i + ticks] === '`') ticks += 1;
      const fence = '`'.repeat(ticks);
      const end = text.indexOf(fence, i + ticks);
      if (end !== -1) {
        flush();
        nodes.push(
          <code
            key={key()}
            className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[13px] text-slate-800"
          >
            {text.slice(i + ticks, end).trim()}
          </code>,
        );
        i = end + ticks;
        continue;
      }
      buffer += fence;
      i += ticks;
      continue;
    }

    const pair = text.startsWith('**', i)
      ? '**'
      : text.startsWith('~~', i)
        ? '~~'
        : null;
    if (pair && text[i + 2] && !/\s/.test(text[i + 2])) {
      const end = findClosing(text, pair, i + 2);
      if (end !== -1) {
        flush();
        const inner = renderInline(text.slice(i + 2, end), key());
        nodes.push(
          pair === '**' ? (
            <strong key={key()} className="font-semibold text-slate-900">
              {inner}
            </strong>
          ) : (
            <del key={key()}>{inner}</del>
          ),
        );
        i = end + 2;
        continue;
      }
    }

    if (
      char === '*' &&
      text[i + 1] !== '*' &&
      text[i + 1] &&
      !/\s/.test(text[i + 1])
    ) {
      let end = findClosing(text, '*', i + 1);
      while (end !== -1 && text[end + 1] === '*')
        end = findClosing(text, '*', end + 2);
      if (end !== -1) {
        flush();
        nodes.push(
          <em key={key()}>{renderInline(text.slice(i + 1, end), key())}</em>,
        );
        i = end + 1;
        continue;
      }
    }

    if (char === '[') {
      const close = text.indexOf('](', i + 1);
      const end = close === -1 ? -1 : text.indexOf(')', close + 2);
      const href = end === -1 ? '' : text.slice(close + 2, end).trim();
      if (end !== -1 && /^https?:\/\/\S+$/i.test(href)) {
        flush();
        nodes.push(
          <a
            key={key()}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky-700 underline underline-offset-2 hover:text-sky-800"
          >
            {renderInline(text.slice(i + 1, close), key())}
          </a>,
        );
        i = end + 1;
        continue;
      }
    }

    buffer += char;
    i += 1;
  }
  flush();
  return nodes;
}

const HEADING_CLASS: Record<number, string> = {
  1: 'mt-6 text-lg font-semibold text-slate-900 first:mt-0',
  2: 'mt-6 text-base font-semibold text-slate-900 first:mt-0',
  3: 'mt-5 text-[15px] font-semibold text-slate-900 first:mt-0',
};

function renderBlocks(
  blocks: Block[],
  keyPrefix: string,
  tight = false,
): ReactNode[] {
  return blocks.map((block, index) => {
    const key = `${keyPrefix}-${index}`;
    switch (block.type) {
      case 'heading': {
        const Tag = `h${Math.min(block.level + 1, 6)}` as 'h2';
        return (
          <Tag
            key={key}
            className={HEADING_CLASS[block.level] ?? HEADING_CLASS[3]}
          >
            {renderInline(block.text, key)}
          </Tag>
        );
      }
      case 'paragraph': {
        const content = block.lines.flatMap((line, lineIndex) => [
          ...(lineIndex ? [<br key={`${key}-br-${lineIndex}`} />] : []),
          ...renderInline(line, `${key}-${lineIndex}`),
        ]);
        return tight ? (
          <div key={key}>{content}</div>
        ) : (
          <p key={key}>{content}</p>
        );
      }
      case 'code':
        return (
          <pre
            key={key}
            className="overflow-x-auto rounded-md bg-slate-900 p-3 font-mono text-[13px] leading-6 text-slate-100"
          >
            <code>{block.text}</code>
          </pre>
        );
      case 'hr':
        return <hr key={key} className="border-slate-200" />;
      case 'quote':
        return (
          <blockquote
            key={key}
            className="space-y-2 border-l-2 border-slate-200 pl-3 text-slate-600"
          >
            {renderBlocks(block.children, key)}
          </blockquote>
        );
      case 'list': {
        const items = block.items.map((item, itemIndex) => (
          <li key={`${key}-${itemIndex}`} className="space-y-1 pl-0.5">
            {renderBlocks(item, `${key}-${itemIndex}`, true)}
          </li>
        ));
        return block.ordered ? (
          <ol
            key={key}
            start={block.start === 1 ? undefined : block.start}
            className="list-decimal space-y-1 pl-5 marker:text-slate-400"
          >
            {items}
          </ol>
        ) : (
          <ul
            key={key}
            className="list-disc space-y-1 pl-5 marker:text-slate-400"
          >
            {items}
          </ul>
        );
      }
      case 'table':
        return (
          <div
            key={key}
            className="overflow-x-auto rounded-md border border-slate-200"
          >
            <table className="w-full border-collapse text-left text-sm leading-6">
              <thead className="bg-slate-50">
                <tr>
                  {block.header.map((cell, cellIndex) => (
                    <th
                      key={cellIndex}
                      style={{ textAlign: block.align[cellIndex] ?? undefined }}
                      className="whitespace-nowrap border-b border-slate-200 px-3 py-2 font-medium text-slate-900"
                    >
                      {renderInline(cell, `${key}-h${cellIndex}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr
                    key={rowIndex}
                    className="border-b border-slate-100 last:border-b-0"
                  >
                    {block.header.map((_, cellIndex) => (
                      <td
                        key={cellIndex}
                        style={{
                          textAlign: block.align[cellIndex] ?? undefined,
                        }}
                        className="px-3 py-1.5 align-top"
                      >
                        {renderInline(
                          row[cellIndex] ?? '',
                          `${key}-${rowIndex}-${cellIndex}`,
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
    }
  });
}

export function Markdown({ text }: { text: string }) {
  const content = useMemo(
    () =>
      renderBlocks(parseBlocks(text.replace(/\r\n?/g, '\n').split('\n')), 'md'),
    [text],
  );
  return (
    <div className="space-y-3 break-words text-[15px] leading-7 text-slate-700">
      {content}
    </div>
  );
}
