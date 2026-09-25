import { createRef } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAttachmentDraft } from '@/hooks/use-attachment-draft';

describe('useAttachmentDraft', () => {
  beforeEach(() => {
    window.sessionStorage.setItem('xiaoyi.csrf-token', 'csrf');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it('uploads, displays, and explicitly removes an unbound attachment', async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.endsWith('/auth/me')) {
        return Response.json({ data: { id: 'u1' }, request_id: 'r' });
      }
      if (init?.method === 'POST') {
        return Response.json({
          data: {
            id: 'a1',
            filename: 'note.txt',
            media_type: 'text/plain',
            size_bytes: 4,
          },
          request_id: 'r',
        });
      }
      return Response.json({
        data: { id: 'a1', deleted: true },
        request_id: 'r',
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() =>
      useAttachmentDraft(createRef<HTMLInputElement>()),
    );

    await act(async () => {
      await result.current.upload(
        new File(['test'], 'note.txt', { type: 'text/plain' }),
      );
    });
    expect(result.current.attachments.map((item) => item.filename)).toEqual([
      'note.txt',
    ]);

    act(() => result.current.remove(result.current.attachments[0]));
    expect(result.current.attachments).toEqual([]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/attachments/a1'),
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('keeps the draft usable after an upload failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/auth/me')) {
          return Response.json({ data: { id: 'u1' }, request_id: 'r' });
        }
        return Response.json(
          {
            error: { code: 'ATTACHMENT_TOO_LARGE', message: '附件过大' },
            request_id: 'r',
          },
          { status: 413 },
        );
      }),
    );
    const { result } = renderHook(() =>
      useAttachmentDraft(createRef<HTMLInputElement>()),
    );

    await act(async () => {
      await result.current.upload(new File(['x'], 'large.txt'));
    });

    expect(result.current.attachments).toEqual([]);
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBe('附件过大');
  });
});
