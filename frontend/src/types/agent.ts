// Agent API request and response types

export interface AgentRequest {
  message: string;
  workspace_dir?: string;
  max_steps?: number;
}

export interface AgentResponse {
  success: boolean;
  message: string;
  steps: number;
  logs: ExecutionLog[];
}

export type ExecutionLogType = 'step' | 'llm_response' | 'tool_call' | 'tool_result' | 'completion' | 'max_steps_reached' | 'error';

export interface ExecutionLog {
  type: ExecutionLogType;

  // step type fields
  step?: number;
  max_steps?: number;
  tokens?: number;
  token_limit?: number;

  // llm_response type fields
  thinking?: string;
  content?: string;
  has_tool_calls?: boolean;
  tool_count?: number;

  // tool_call type fields
  tool?: string;
  arguments?: Record<string, any>;

  // tool_result type fields
  success?: boolean;
  error?: string;
  execution_time?: number;

  // completion/error type fields
  message?: string;
}

// Stream event types
export type StreamEventType =
  | 'log_file'
  | 'step'
  | 'thinking'
  | 'content'
  | 'tool_call'
  | 'tool_result'
  | 'done'
  | 'error';

export interface StreamEvent {
  type: StreamEventType;
  data: Record<string, any>;
}

export interface StreamStepData {
  step: number;
  max_steps: number;
  tokens: number;
  token_limit: number;
}

export interface StreamDeltaData {
  delta: string;
}

export interface StreamToolCallData {
  tool: string;
  arguments: Record<string, any>;
}

export interface StreamToolResultData {
  tool: string;
  success: boolean;
  content?: string;
  error?: string;
  execution_time: number;
}

export interface StreamDoneData {
  message: string;
  steps: number;
  reason: string;
}

export interface StreamErrorData {
  message: string;
  reason?: string;
}
