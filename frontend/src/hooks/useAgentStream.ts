// Hook for streaming agent execution
import { useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { SSEClient } from '@/services/sse';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import type { AgentRequest, StreamEvent } from '@/types/agent';
import type { Message } from '@/types/message';

export function useAgentStream() {
  const sseClient = useRef<SSEClient>(new SSEClient());
  const chatStore = useChatStore();
  const sessionStore = useSessionStore();

  const sendMessage = useCallback(
    async (content: string, max_steps?: number) => {
      const currentSession = sessionStore.getCurrentSession();
      if (!currentSession) {
        console.error('No active session');
        return;
      }

      // Add user message
      const userMessage: Message = {
        id: uuidv4(),
        role: 'user',
        content,
        timestamp: new Date(),
      };
      sessionStore.addMessageToSession(currentSession.id, userMessage);

      // Start streaming assistant message
      const assistantMessageId = uuidv4();
      chatStore.startStreaming(assistantMessageId);

      // Prepare request
      const request: AgentRequest = {
        message: content,
        max_steps: max_steps || 50,
      };

      try {
        await sseClient.current.stream(
          request,
          (event: StreamEvent) => {
            handleStreamEvent(event);
          },
          (error: Error) => {
            console.error('Stream error:', error);
            chatStore.stopStreaming();
          }
        );

        // Stream completed, add final message to session
        const finalMessage = chatStore.getStreamingMessage();
        if (finalMessage) {
          sessionStore.addMessageToSession(currentSession.id, {
            ...finalMessage,
            isStreaming: false,
          });
        }

        chatStore.reset();
      } catch (error) {
        console.error('Failed to send message:', error);
        chatStore.stopStreaming();
      }
    },
    [sessionStore, chatStore]
  );

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      const { type, data } = event;

      switch (type) {
        case 'step':
          chatStore.setStepInfo(data.step, data.max_steps);
          chatStore.setTokenInfo(data.tokens, data.token_limit);
          break;

        case 'thinking':
          chatStore.appendThinking(data.delta);
          break;

        case 'content':
          chatStore.appendContent(data.delta);
          break;

        case 'tool_call':
          chatStore.addToolCall({
            tool: data.tool,
            arguments: data.arguments,
          });
          break;

        case 'tool_result':
          chatStore.updateToolResult(data.tool, {
            success: data.success,
            content: data.content,
            error: data.error,
            execution_time: data.execution_time,
          });
          break;

        case 'done':
          chatStore.stopStreaming();
          break;

        case 'error':
          console.error('Stream error:', data.message);
          chatStore.stopStreaming();
          break;
      }
    },
    [chatStore]
  );

  const cancelStream = useCallback(() => {
    sseClient.current.cancel();
    chatStore.stopStreaming();
  }, [chatStore]);

  return {
    sendMessage,
    cancelStream,
    isStreaming: chatStore.isStreaming,
    currentStep: chatStore.currentStep,
    maxSteps: chatStore.maxSteps,
    tokenUsage: chatStore.tokenUsage,
    tokenLimit: chatStore.tokenLimit,
  };
}
