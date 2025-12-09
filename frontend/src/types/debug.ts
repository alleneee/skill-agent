export interface RunListItem {
  run_id: string;
  timestamp: string;
  total_steps: number;
  total_tool_calls: number;
  total_events: number;
  success: boolean;
  final_token_count: number;
}

export interface RunSummary {
  run_id: string;
  timestamp: string;
  total_steps: number;
  total_tool_calls: number;
  total_events: number;
  success: boolean;
  final_token_count: number;
  total_requests?: number;
}

export interface RunEvent {
  type: string;
  index: number;
  run_id: string;
  logged_at: string;
  data: RunEventData;
}

export interface RunEventData {
  run_id?: string;
  step?: number;
  max_steps?: number;
  token_count?: number;
  token_limit?: number;
  token_usage_percent?: number;
  messages?: MessageData[];
  tools?: string[];
  content?: string;
  thinking?: string;
  tool_calls?: ToolCallData[];
  tool_name?: string;
  arguments?: Record<string, unknown>;
  success?: boolean;
  result?: string;
  result_length?: number;
  error?: string;
  execution_time_seconds?: number;
  final_response?: string;
  total_steps?: number;
  reason?: string;
  input_tokens?: number;
  output_tokens?: number;
  finish_reason?: string;
}

export interface MessageData {
  role: string;
  content: string;
  thinking?: string;
  tool_calls?: ToolCallData[];
  tool_call_id?: string;
  name?: string;
}

export interface ToolCallData {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: Record<string, unknown>;
  };
}

export interface RunDetail {
  run_id: string;
  summary: RunSummary;
  events: RunEvent[];
}
