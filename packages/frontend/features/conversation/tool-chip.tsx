'use client';

import { useState } from 'react';
import { Check, ChevronDown, Loader2 } from 'lucide-react';

import { getRunArtifact } from '@/lib/api';
import type { ToolCallInfo } from '@/hooks/use-conversation-messages';

type Citation = { title: string; source: string; score: number | null };

const JSON_PREVIEW_LIMIT = 4000;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function toCitation(item: unknown): Citation | null {
  const record = asRecord(item);
  if (!record) return null;
  const source = record.source ?? record.source_type;
  if (typeof source !== 'string' || !source) return null;
  const id = typeof record.id === 'string' ? record.id : '';
  const sourceId = typeof record.source_id === 'string' ? record.source_id : '';
  const title =
    typeof record.title === 'string' && record.title ? record.title : id || sourceId;
  if (!title) return null;
  return {
    title,
    source,
    score: typeof record.score === 'number' ? record.score : null,
  };
}

/**
 * 从工具输出中提取引用条目：search_knowledge → data.results，
 * diagnose_fault → data.sources（诊断结果或 rediagnosis 内嵌）。
 * 结构不匹配时返回 null，由调用方回退到原始 JSON 展示。
 */
export function extractCitations(content: unknown): Citation[] | null {
  const root = asRecord(content);
  const data = root ? asRecord(root.data) : null;
  for (const container of [data, root]) {
    if (!container) continue;
    for (const key of ['results', 'sources'] as const) {
      const list = container[key];
      if (!Array.isArray(list)) continue;
      const items = list
        .map(toCitation)
        .filter((item): item is Citation => item !== null);
      if (items.length) return items;
    }
  }
  return null;
}

function formatJson(content: unknown) {
  const text = JSON.stringify(content, null, 2) ?? '';
  return text.length > JSON_PREVIEW_LIMIT
    ? `${text.slice(0, JSON_PREVIEW_LIMIT)}\n…（已截断）`
    : text;
}

export function ToolChip({ tool }: { tool: ToolCallInfo }) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // undefined 表示尚未加载；artifact 内容只在首次展开时拉取一次
  const [content, setContent] = useState<unknown>(undefined);

  const expandable = Boolean(tool.artifactId || tool.output !== undefined);

  async function toggle() {
    if (!expandable) return;
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (content !== undefined || tool.output !== undefined) return;
    if (!tool.runId || !tool.artifactId) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await getRunArtifact(tool.runId, tool.artifactId);
      setContent(detail.content);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  // 已加载的工件内容优先；未转存的 inline 输出直接展示
  const displayContent = content !== undefined ? content : tool.output;
  const citations = expandable ? extractCitations(displayContent) : null;

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={expandable ? expanded : undefined}
        className={`flex w-full items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs ${
          expandable ? 'cursor-pointer hover:bg-slate-100' : 'cursor-default'
        }`}
      >
        <span className="grid size-5 place-items-center rounded bg-emerald-100 text-emerald-700">
          <Check className="size-3" />
        </span>
        <span className="font-medium text-slate-700">{tool.name}</span>
        <span className="min-w-0 flex-1 truncate text-slate-400">
          {tool.result}
        </span>
        {expandable ? (
          <ChevronDown
            className={`size-3.5 text-slate-400 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        ) : null}
      </button>
      {expanded && expandable ? (
        <div className="mt-1 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs">
          {loading ? (
            <p className="flex items-center gap-1.5 text-slate-400">
              <Loader2 className="size-3 animate-spin" />
              正在加载完整输出…
            </p>
          ) : error ? (
            <p className="text-red-600">{error}</p>
          ) : citations?.length ? (
            <div className="space-y-1.5">
              <p className="text-slate-400">引用来源</p>
              <ul className="space-y-1">
                {citations.map((item, index) => (
                  <li
                    key={`${item.source}-${item.title}-${index}`}
                    className="flex min-w-0 items-baseline gap-2"
                  >
                    <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                      {item.source}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-slate-700">
                      {item.title}
                    </span>
                    {item.score !== null ? (
                      <span className="shrink-0 font-mono text-slate-400">
                        {item.score.toFixed(4)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-[11px] leading-5 text-slate-600">
              {formatJson(displayContent)}
            </pre>
          )}
        </div>
      ) : null}
    </div>
  );
}
