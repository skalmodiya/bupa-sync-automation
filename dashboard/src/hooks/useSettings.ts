import { useState, useEffect, useCallback } from 'react';
import type { Settings } from '../types';
import { api } from '../lib/api';

const defaultSettings: Settings = {
  llm: {
    provider: 'local-proxy',
    baseUrl: 'http://localhost:6655/litellm/v1',
    model: 'anthropic--claude-4.6-sonnet',
    apiKey: '',
  },
  n8n: {
    url: 'http://localhost:5678',
    apiKey: '',
    workflowId: '',
    retryWorkflowId: '',
    agentFixWorkflowId: '',
    monitoredWorkflowIds: [],
    webhookUrl: '',
  },
  mockS4hana: {
    serverUrl: 'http://localhost:8090',
  },
  deployment: {
    mode: 'local',
  },
  email: {
    smtpHost: 'localhost',
    smtpPort: 1025,
    username: '',
    password: '',
  },
  auth: {
    iasUrl: '',
    clientId: '',
    clientSecret: '',
  },
};

/** Map backend snake_case response to frontend camelCase Settings */
function fromBackend(data: any): Settings {
  return {
    llm: {
      provider: data?.llm?.provider || defaultSettings.llm.provider,
      baseUrl: data?.llm?.base_url || data?.llm?.baseUrl || defaultSettings.llm.baseUrl,
      model: data?.llm?.model || defaultSettings.llm.model,
      apiKey: data?.llm?.api_key || data?.llm?.apiKey || '',
    },
    n8n: {
      url: data?.n8n?.url || defaultSettings.n8n.url,
      apiKey: data?.n8n?.api_key || data?.n8n?.apiKey || '',
      workflowId: data?.n8n?.workflow_id || data?.n8n?.workflowId || '',
      retryWorkflowId: data?.n8n?.retry_workflow_id || data?.n8n?.retryWorkflowId || '',
      agentFixWorkflowId: data?.n8n?.agent_fix_workflow_id || data?.n8n?.agentFixWorkflowId || '',
      monitoredWorkflowIds: data?.n8n?.monitored_workflow_ids || data?.n8n?.monitoredWorkflowIds || [],
      webhookUrl: data?.n8n?.webhook_url || data?.n8n?.webhookUrl || '',
    },
    mockS4hana: {
      serverUrl: data?.mock_s4?.url || data?.mockS4hana?.serverUrl || defaultSettings.mockS4hana.serverUrl,
    },
    deployment: {
      mode: data?.deployment_mode || data?.deployment?.mode || 'local',
    },
    email: {
      smtpHost: data?.smtp?.host || data?.email?.smtpHost || '',
      smtpPort: data?.smtp?.port || data?.email?.smtpPort || 1025,
      username: data?.smtp?.username || data?.email?.username || '',
      password: data?.smtp?.password || data?.email?.password || '',
    },
    auth: {
      iasUrl: data?.auth?.ias_url || data?.auth?.iasUrl || '',
      clientId: data?.auth?.client_id || data?.auth?.clientId || '',
      clientSecret: data?.auth?.client_secret || data?.auth?.clientSecret || '',
    },
  };
}

/** Map frontend camelCase Settings to backend snake_case for PUT */
function toBackend(settings: Settings): any {
  return {
    deployment_mode: settings.deployment.mode,
    llm: {
      provider: settings.llm.provider,
      base_url: settings.llm.baseUrl,
      model: settings.llm.model,
      api_key: settings.llm.apiKey,
    },
    n8n: {
      url: settings.n8n.url,
      api_key: settings.n8n.apiKey,
      workflow_id: settings.n8n.workflowId,
      retry_workflow_id: settings.n8n.retryWorkflowId,
      agent_fix_workflow_id: settings.n8n.agentFixWorkflowId,
      monitored_workflow_ids: settings.n8n.monitoredWorkflowIds,
      webhook_url: settings.n8n.webhookUrl,
    },
    mock_s4: {
      url: settings.mockS4hana.serverUrl,
    },
    smtp: {
      host: settings.email.smtpHost,
      port: settings.email.smtpPort,
      username: settings.email.username,
      password: settings.email.password,
    },
    agent: {
      url: 'http://localhost:5000',
    },
    auth: {
      ias_url: settings.auth.iasUrl,
      client_id: settings.auth.clientId,
      client_secret: settings.auth.clientSecret,
    },
  };
}

export function useSettings() {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    const res = await api.get<any>('/api/settings');
    if (res.ok && res.data) {
      setSettings(fromBackend(res.data));
    } else if (res.error) {
      setError(res.error);
    }
    setLoading(false);
  }, []);

  const saveSettings = useCallback(async (newSettings: Settings) => {
    setSaving(true);
    setError(null);
    const res = await api.put<any>('/api/settings', toBackend(newSettings));
    if (res.ok) {
      setSettings(newSettings);
    } else {
      setError(res.error || 'Failed to save settings');
    }
    setSaving(false);
    return res.ok;
  }, []);

  const testConnection = useCallback(async (type: 'llm' | 'n8n' | 's4hana' | 'email') => {
    const endpoint = type === 's4hana' ? 'test-s4' : type === 'llm' ? 'test-llm' : type === 'n8n' ? 'test-n8n' : 'test-smtp';
    const res = await api.post<{ success: boolean; message: string }>(
      `/api/settings/${endpoint}`,
      toBackend(settings)
    );
    return res;
  }, [settings]);

  const sendTestEmail = useCallback(async () => {
    const res = await api.post<{ status: string; message: string }>(
      '/api/settings/send-test-email',
      toBackend(settings)
    );
    return res;
  }, [settings]);

  const fetchN8nWorkflows = useCallback(async (overrideSettings?: Settings) => {
    const s = overrideSettings || settings;
    const res = await api.post<{ workflows?: Array<{ id: string; name: string; active: boolean }>; error?: string }>(
      '/api/settings/fetch-n8n-workflows',
      toBackend(s)
    );
    return res;
  }, [settings]);

  const fetchLlmModels = useCallback(async (overrideSettings?: Settings) => {
    const s = overrideSettings || settings;
    const res = await api.post<{ models?: Array<{ id: string; name: string }>; error?: string }>(
      '/api/settings/fetch-llm-models',
      toBackend(s)
    );
    return res;
  }, [settings]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  return {
    settings,
    setSettings,
    loading,
    saving,
    error,
    saveSettings,
    testConnection,
    sendTestEmail,
    fetchN8nWorkflows,
    fetchLlmModels,
    loadSettings,
  };
}
