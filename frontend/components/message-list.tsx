'use client';

import {
  Check,
  ChevronDown,
  CircleUserRound,
  FileSearch,
  FileText,
  Loader2,
  Sparkles,
} from 'lucide-react';

import { RemediationCard } from '@/components/remediation-card';
import { Button } from '@/components/ui/button';
import type { ChatMessage } from '@/hooks/use-conversation-messages';

type MessageListProps = {
  messages: ChatMessage[];
  running: boolean;
  hasMore: boolean;
  loadingEarlier: boolean;
  earlierError: string | null;
  onLoadEarlier: () => void;
};

export function MessageList({
  messages,
  running,
  hasMore,
  loadingEarlier,
  earlierError,
  onLoadEarlier,
}: MessageListProps) {
  return (
    <div className="mx-auto w-full max-w-3xl px-5 pb-40 pt-8 sm:px-8">
      {hasMore ? (
        <div className="mb-6 flex flex-col items-center gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loadingEarlier}
            className="border-slate-200 text-slate-600 shadow-none"
            onClick={onLoadEarlier}
          >
            {loadingEarlier ? <Loader2 className="animate-spin" /> : null}
            加载更早消息
          </Button>
          {earlierError ? (
            <p className="text-xs text-red-600">{earlierError}</p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-8">
        {messages.map((message) => (
          <article
            key={message.id}
            className="grid grid-cols-[32px_minmax(0,1fr)] gap-3 sm:gap-4"
          >
            <span
              className={`grid size-8 place-items-center rounded-md ${message.role === 'assistant' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`}
            >
              {message.role === 'assistant' ? (
                <Sparkles className="size-4" />
              ) : (
                <CircleUserRound className="size-4" />
              )}
            </span>
            <div className="min-w-0 pt-1">
              <p className="mb-2 text-sm font-medium text-slate-900">
                {message.role === 'assistant' ? '小yi' : '你'}
              </p>
              {message.tools ? (
                <div className="mb-4 space-y-1.5">
                  {message.tools.map((tool) => (
                    <button
                      key={tool.name}
                      type="button"
                      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs"
                    >
                      <span className="grid size-5 place-items-center rounded bg-emerald-100 text-emerald-700">
                        <Check className="size-3" />
                      </span>
                      <span className="font-medium text-slate-700">
                        {tool.name}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-slate-400">
                        {tool.result}
                      </span>
                      <ChevronDown className="size-3.5 text-slate-400" />
                    </button>
                  ))}
                </div>
              ) : null}
              <p className="whitespace-pre-wrap text-[15px] leading-7 text-slate-700">
                {message.text}
              </p>
              {message.proposals?.length ? (
                <div className="mt-2 space-y-2">
                  {message.proposals.map((proposal) => (
                    <RemediationCard
                      key={proposal.proposal_id}
                      proposal={proposal}
                    />
                  ))}
                </div>
              ) : null}
              {message.attachments?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {message.attachments.map((attachment) => (
                    <span
                      key={attachment.id}
                      className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600"
                    >
                      <FileText className="size-3.5" />
                      {attachment.filename}
                    </span>
                  ))}
                </div>
              ) : null}
              {message.citation ? (
                <button
                  type="button"
                  className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 hover:bg-slate-50"
                >
                  <FileSearch className="mr-1.5 inline size-3.5" />
                  {message.citation}
                </button>
              ) : null}
            </div>
          </article>
        ))}
        {running &&
        (messages.at(-1)?.role !== 'assistant' || !messages.at(-1)?.text) ? (
          <article className="grid grid-cols-[32px_minmax(0,1fr)] gap-4">
            <span className="grid size-8 place-items-center rounded-md bg-slate-900 text-white">
              <Sparkles className="size-4" />
            </span>
            <div className="pt-2">
              <div className="flex items-center gap-1.5">
                <span className="size-1.5 animate-pulse rounded-full bg-slate-400" />
                <span className="size-1.5 animate-pulse rounded-full bg-slate-400 [animation-delay:120ms]" />
                <span className="size-1.5 animate-pulse rounded-full bg-slate-400 [animation-delay:240ms]" />
              </div>
            </div>
          </article>
        ) : null}
      </div>
    </div>
  );
}
