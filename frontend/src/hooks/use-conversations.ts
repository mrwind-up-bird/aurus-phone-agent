"use client";

import { useState, useCallback, useEffect } from "react";
import type { ConversationSummary, ConversationDetail } from "@/lib/types";

interface UseConversationsReturn {
  conversations: ConversationSummary[];
  selectedConversation: ConversationDetail | null;
  loadDetail: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
  isLoading: boolean;
  isLoadingDetail: boolean;
  clearSelection: () => void;
}

export function useConversations(): UseConversationsReturn {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversation, setSelectedConversation] =
    useState<ConversationDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/conversations");
      if (res.ok) {
        const data = await res.json();
        setConversations(data.conversations ?? []);
      }
    } catch (err) {
      console.error("Failed to fetch conversations:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setIsLoadingDetail(true);
    try {
      const res = await fetch(`/api/conversations/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedConversation(data.conversation ?? null);
      }
    } catch (err) {
      console.error("Failed to fetch conversation detail:", err);
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedConversation(null);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    conversations,
    selectedConversation,
    loadDetail,
    refresh,
    isLoading,
    isLoadingDetail,
    clearSelection,
  };
}
