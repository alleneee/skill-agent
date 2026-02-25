// Agent API 服务
import apiClient from './api';
import type { AgentRequest, AgentResponse } from '@/types/agent';

interface CancelRequest {
  run_id?: string;
  session_id?: string;
}

interface CancelResponse {
  success: boolean;
  message: string;
  cancelled_runs: string[];
}

export const agentService = {
  async run(request: AgentRequest): Promise<AgentResponse> {
    const { data } = await apiClient.post<AgentResponse>('/agent/run', request);
    return data;
  },

  async cancel(request: CancelRequest): Promise<CancelResponse> {
    const { data } = await apiClient.post<CancelResponse>('/agent/cancel', request);
    return data;
  },

  async health(): Promise<{ status: string }> {
    const { data } = await apiClient.get('/health');
    return data;
  },

  async getTools(): Promise<any> {
    const { data } = await apiClient.get('/tools/');
    return data;
  },
};
