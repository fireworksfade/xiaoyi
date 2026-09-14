'use client';

import { useCallback, useState, type RefObject } from 'react';

import {
  deleteAttachment,
  ensureDemoSession,
  uploadAttachment,
  type UploadedAttachment,
} from '@/lib/api';

export function useAttachmentDraft(
  fileInputRef: RefObject<HTMLInputElement | null>,
) {
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      await ensureDemoSession();
      const uploaded = await uploadAttachment(file);
      setAttachments((current) => [...current, uploaded].slice(0, 5));
    } catch (uploadError) {
      setError(
        uploadError instanceof Error ? uploadError.message : '附件上传失败',
      );
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  const remove = useCallback((attachment: UploadedAttachment) => {
    setAttachments((current) =>
      current.filter((item) => item.id !== attachment.id),
    );
    void deleteAttachment(attachment.id).catch(() => {});
  }, []);

  const reset = useCallback(() => {
    setAttachments([]);
    setError(null);
  }, []);

  return {
    attachments,
    setAttachments,
    busy,
    error,
    setError,
    upload,
    remove,
    reset,
  };
}
