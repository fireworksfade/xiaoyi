'use client';

import { useCallback, useState } from 'react';

import { listConversations, type Conversation } from '@/lib/api';

export function useConversationList() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const page = await listConversations();
    setConversations(page.items);
    return page.items;
  }, []);

  const refresh = useCallback(
    async (preferredId?: string | null) => {
      const items = await load();
      return (
        items.find((conversation) => conversation.id === preferredId) ?? null
      );
    },
    [load],
  );

  const prepend = useCallback((conversation: Conversation) => {
    setConversations((current) => [
      conversation,
      ...current.filter((item) => item.id !== conversation.id),
    ]);
  }, []);

  const update = useCallback((conversation: Conversation) => {
    setConversations((current) =>
      current.map((item) =>
        item.id === conversation.id ? conversation : item,
      ),
    );
  }, []);

  const remove = useCallback((id: string) => {
    setConversations((current) =>
      current.filter((conversation) => conversation.id !== id),
    );
  }, []);

  return {
    conversations,
    setConversations,
    busy,
    setBusy,
    error,
    setError,
    load,
    refresh,
    prepend,
    update,
    remove,
  };
}
