import type { RunListItem, RunDetail } from '@/types/debug';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function fetchRuns(limit = 50): Promise<RunListItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/trace/runs/list?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch runs');
  return res.json();
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const res = await fetch(`${API_BASE}/api/v1/trace/runs/detail/${runId}`);
  if (!res.ok) throw new Error('Failed to fetch run detail');
  return res.json();
}

export async function deleteRun(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/trace/runs/${runId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete run');
}

export interface SendRequestOptions {
  message: string;
  useTravelTeam?: boolean;
}

export async function sendAgentRequest(options: SendRequestOptions): Promise<unknown> {
  const { message, useTravelTeam } = options;

  const endpoint = useTravelTeam
    ? `${API_BASE}/api/v1/team/run`
    : `${API_BASE}/api/v1/agent/run`;

  const body = useTravelTeam
    ? { message, team_name: 'travel_team', members: ['researcher', 'writer'] }
    : { message };

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Request failed');
  }

  return res.json();
}
