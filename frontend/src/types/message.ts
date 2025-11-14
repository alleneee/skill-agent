// Message types for chat interface

export type MessageRole = 'user' | 'assistant';

export interface ToolCall {
  tool: string;
  arguments: Record<string, any>;
  result?: {
    success: boolean;
    content?: string;
    error?: string;
    execution_time?: number;
  };
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  thinking?: string;
  toolCalls?: ToolCall[];
  timestamp: Date;
  isStreaming?: boolean;
}
