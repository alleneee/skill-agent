import { useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { SSEClient } from '@/services/sse';
import { agentService } from '@/services/agent';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import type { AgentRequest, StreamEvent, UserInputField } from '@/types/agent';
import type { Message } from '@/types/message';

export function useAgentStream() {
  const sseClient = useRef<SSEClient>(new SSEClient());
  const currentRunId = useRef<string | null>(null);
  const chatStore = useChatStore();
  const sessionStore = useSessionStore();

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      const { type, data } = event;

      switch (type) {
        case 'run_started':
          currentRunId.current = data.run_id;
          break;

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

        case 'user_input_required':
          chatStore.setPendingUserInput({
            toolCallId: data.tool_call_id,
            fields: data.fields as UserInputField[],
            context: data.context,
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

  const sendMessage = useCallback(
    async (content: string) => {
      let currentSession = sessionStore.getCurrentSession();
      if (!currentSession) {
        currentSession = sessionStore.createSession('新对话');
      }

      const userMessage: Message = {
        id: uuidv4(),
        role: 'user',
        content,
        timestamp: new Date(),
      };
      sessionStore.addMessageToSession(currentSession.id, userMessage);

      const assistantMessageId = uuidv4();
      chatStore.startStreaming(assistantMessageId);

      const request: AgentRequest = {
        message: content,
        session_id: currentSession.id,
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
    [sessionStore, chatStore, handleStreamEvent]
  );

  const cancelStream = useCallback(async () => {
    sseClient.current.cancel();
    if (currentRunId.current) {
      try {
        await agentService.cancel({ run_id: currentRunId.current });
      } catch (e) {
        console.error('Failed to cancel run:', e);
      }
      currentRunId.current = null;
    }
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
    pendingUserInput: chatStore.pendingUserInput,
    isWaitingForInput: chatStore.isWaitingForInput,
    clearPendingUserInput: chatStore.clearPendingUserInput,
  };
}
