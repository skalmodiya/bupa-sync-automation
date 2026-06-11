export interface Settings {
  llm: {
    provider: 'local-proxy' | 'sap-ai-core';
    baseUrl: string;
    model: string;
    apiKey: string;
  };
  n8n: {
    url: string;
    apiKey: string;
    workflowId: string;
    retryWorkflowId: string;
    agentFixWorkflowId: string;
    monitoredWorkflowIds: string[];
    webhookUrl: string;
  };
  mockS4hana: {
    serverUrl: string;
  };
  deployment: {
    mode: 'local' | 'docker' | 'production';
  };
  email: {
    smtpHost: string;
    smtpPort: number;
    username: string;
    password: string;
  };
  auth: {
    iasUrl: string;
    clientId: string;
    clientSecret: string;
  };
}

export interface AuthStatus {
  ias_configured: boolean;
  authenticated: boolean;
  user: { name: string; email: string } | null;
  login_url: string | null;
}

export interface N8nWorkflow {
  id: string;
  name: string;
  active: boolean;
}

export interface LLMModel {
  id: string;
  name: string;
}

export interface N8nExecution {
  id: string;
  finished: boolean;
  mode: string;
  startedAt: string;
  stoppedAt: string | null;
  workflowId: string;
  workflowName: string;
  status: 'success' | 'error' | 'running' | 'waiting' | 'unknown';
  data?: Record<string, unknown>;
}

export interface AgentHealth {
  status: 'healthy' | 'degraded' | 'offline';
  uptime?: number;
  version?: string;
  lastCheck: string;
}

export interface AgentInfo {
  name: string;
  title?: string;
  description: string;
  version: string;
  capabilities: string[];
  skills?: Array<{ id: string; name: string; description: string; tags?: string[] }>;
}

export interface AgentInvocation {
  id: string;
  timestamp: string;
  message: string;
  response: string;
  tokenUsage: {
    input: number;
    output: number;
    total: number;
  };
  duration: number;
}

export interface SyncStatus {
  totalEmployees: number;
  synced: number;
  failed: number;
  pending: number;
  lastRun: string;
  errors: SyncError[];
  recentActivity: ActivityEntry[];
}

export interface SyncError {
  category: string;
  count: number;
  percentage: number;
}

export interface ActivityEntry {
  id: string;
  timestamp: string;
  action: string;
  status: 'success' | 'error' | 'warning';
  details: string;
}

export interface ApiResponse<T> {
  data?: T;
  error?: string;
  ok: boolean;
}
