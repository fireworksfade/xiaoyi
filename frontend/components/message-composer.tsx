'use client';

import type { RefObject } from 'react';
import {
  ArrowUp,
  ChevronDown,
  FileText,
  Loader2,
  Paperclip,
  Wrench,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Textarea } from '@/components/ui/textarea';
import type { ToolSource, UploadedAttachment } from '@/lib/api';

type MessageComposerProps = {
  input: string;
  running: boolean;
  attachments: UploadedAttachment[];
  attachmentBusy: boolean;
  error: string | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  toolSources: ToolSource[];
  toolSelection: string;
  toolMenuOpen: boolean;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onFile: (file: File) => void;
  onRemoveAttachment: (attachment: UploadedAttachment) => void;
  onToolMenuOpenChange: (open: boolean) => void;
  onToolSelectionChange: (value: string) => void;
};

export function MessageComposer({
  input,
  running,
  attachments,
  attachmentBusy,
  error,
  fileInputRef,
  toolSources,
  toolSelection,
  toolMenuOpen,
  onInputChange,
  onSubmit,
  onFile,
  onRemoveAttachment,
  onToolMenuOpenChange,
  onToolSelectionChange,
}: MessageComposerProps) {
  const toolSelectionLabel =
    toolSelection === 'none'
      ? '不使用工具'
      : toolSelection.startsWith('server:')
        ? (toolSources.find(
            (source) => source.id === toolSelection.slice('server:'.length),
          )?.name ?? '指定服务')
        : '工具自动选择';

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-white via-white to-transparent px-4 pb-5 pt-12">
      <form
        className="pointer-events-auto mx-auto max-w-3xl"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="rounded-xl border border-slate-300 bg-white p-2 shadow-[0_8px_30px_rgba(15,23,42,.08)] focus-within:border-slate-400">
          {attachments.length ? (
            <div className="flex flex-wrap gap-2 px-2 pb-2 pt-1">
              {attachments.map((attachment) => (
                <span
                  key={attachment.id}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-600"
                >
                  <FileText className="size-3.5 shrink-0" />
                  <span className="max-w-48 truncate">
                    {attachment.filename}
                  </span>
                  <button
                    type="button"
                    aria-label={`移除 ${attachment.filename}`}
                    className="rounded p-0.5 hover:bg-slate-200"
                    onClick={() => onRemoveAttachment(attachment)}
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            </div>
          ) : null}
          <Textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                onSubmit();
              }
            }}
            placeholder="给小yi发送消息"
            className="max-h-36 min-h-12 resize-none border-0 bg-transparent px-2 py-2 text-[15px] shadow-none focus-visible:ring-0"
          />
          <div className="flex items-center justify-between px-1 pb-0.5">
            <div className="flex items-center gap-1">
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onFile(file);
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled={attachmentBusy || attachments.length >= 5}
                className="size-8 text-slate-500 hover:bg-slate-100"
                onClick={() => fileInputRef.current?.click()}
              >
                {attachmentBusy ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Paperclip />
                )}
                <span className="sr-only">添加附件</span>
              </Button>
              <DropdownMenu
                open={toolMenuOpen}
                onOpenChange={onToolMenuOpenChange}
              >
                <DropdownMenuTrigger
                  render={
                    <button
                      type="button"
                      aria-label="选择本次消息使用的工具"
                      className="flex h-8 max-w-44 items-center gap-1.5 rounded-md px-2 text-xs text-slate-500 hover:bg-slate-100"
                    />
                  }
                >
                  <Wrench className="size-3.5" />
                  <span className="truncate">{toolSelectionLabel}</span>
                  <ChevronDown className="size-3.5 shrink-0" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" side="top" className="w-64">
                  <DropdownMenuRadioGroup
                    value={toolSelection}
                    onValueChange={(value) =>
                      onToolSelectionChange(String(value))
                    }
                  >
                    <DropdownMenuLabel>本次消息使用的工具</DropdownMenuLabel>
                    <DropdownMenuRadioItem value="auto">
                      自动选择全部已授权工具
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="none">
                      不使用工具
                    </DropdownMenuRadioItem>
                    {toolSources.length ? <DropdownMenuSeparator /> : null}
                    {toolSources.map((source) => (
                      <DropdownMenuRadioItem
                        key={source.id}
                        value={`server:${source.id}`}
                      >
                        <span className="min-w-0 flex-1 truncate">
                          {source.name}
                        </span>
                        <span className="text-xs text-slate-400">
                          {source.tool_count}
                        </span>
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || running}
              className="size-8 rounded-md bg-slate-900 text-white hover:bg-slate-700"
            >
              <ArrowUp />
              <span className="sr-only">发送消息</span>
            </Button>
          </div>
        </div>
        {error ? (
          <p className="mt-2 text-center text-xs text-red-600">{error}</p>
        ) : null}
        <p className="mt-2 text-center text-[11px] text-slate-400">
          工具输出可能出错；受控操作需要人工审批。
        </p>
      </form>
    </div>
  );
}
