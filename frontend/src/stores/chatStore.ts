// Chat state management store using Zustand
import { create } from 'zustand';
import type { Message, ToolCall } from '@/types/message';

interface ChatState {
  // Current message being streamed
  streamingMessage: Message | null;
  isStreaming: boolean;

  // Execution status
  currentStep: number;
  maxSteps: number;
  tokenUsage: number;
  tokenLimit: number;

  // Actions
  startStreaming: (messageId: string) => void;
  stopStreaming: () => void;
  appendThinking: (delta: string) => void;
  appendContent: (delta: string) => void;
  addToolCall: (toolCall: ToolCall) => void;
  updateToolResult: (
    toolName: string,
    result: { success: boolean; content?: string; error?: string; execution_time?: number }
  ) => void;
  setStepInfo: (current: number, max: number) => void;
  setTokenInfo: (usage: number, limit: number) => void;
  reset: () => void;
  getStreamingMessage: () => Message | null;
}

export const useChatStore = create<ChatState>((set, get) => ({
  streamingMessage: null,
  isStreaming: false,
  currentStep: 0,
  maxSteps: 50,
  tokenUsage: 0,
  tokenLimit: 120000,

  startStreaming: (messageId: string) => {
    set({
      streamingMessage: {
        id: messageId,
        role: 'assistant',
        content: '',
        thinking: '',
        toolCalls: [],
        timestamp: new Date(),
        isStreaming: true,
      },
      isStreaming: true,
    });
  },

  stopStreaming: () => {
    set((state) => ({
      streamingMessage: state.streamingMessage
        ? { ...state.streamingMessage, isStreaming: false }
        : null,
      isStreaming: false,
    }));
  },

  appendThinking: (delta: string) => {
    set((state) => {
      if (!state.streamingMessage) return state;
      return {
        streamingMessage: {
          ...state.streamingMessage,
          thinking: (state.streamingMessage.thinking || '') + delta,
        },
      };
    });
  },

  appendContent: (delta: string) => {
    set((state) => {
      if (!state.streamingMessage) return state;
      return {
        streamingMessage: {
          ...state.streamingMessage,
          content: state.streamingMessage.content + delta,
        },
      };
    });
  },

  addToolCall: (toolCall: ToolCall) => {
    set((state) => {
      if (!state.streamingMessage) return state;
      return {
        streamingMessage: {
          ...state.streamingMessage,
          toolCalls: [...(state.streamingMessage.toolCalls || []), toolCall],
        },
      };
    });
  },

  updateToolResult: (toolName: string, result) => {
    set((state) => {
      if (!state.streamingMessage || !state.streamingMessage.toolCalls) return state;

      const updatedToolCalls = state.streamingMessage.toolCalls.map((tc) =>
        tc.tool === toolName ? { ...tc, result } : tc
      );

      return {
        streamingMessage: {
          ...state.streamingMessage,
          toolCalls: updatedToolCalls,
        },
      };
    });
  },

  setStepInfo: (current: number, max: number) => {
    set({ currentStep: current, maxSteps: max });
  },

  setTokenInfo: (usage: number, limit: number) => {
    set({ tokenUsage: usage, tokenLimit: limit });
  },

  reset: () => {
    set({
      streamingMessage: null,
      isStreaming: false,
      currentStep: 0,
      maxSteps: 50,
      tokenUsage: 0,
      tokenLimit: 120000,
    });
  },

  getStreamingMessage: () => {
    return get().streamingMessage;
  },
}));
