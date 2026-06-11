import { useState, useEffect } from 'react';
import { useSettings } from '../hooks/useSettings';
import { useDashboardConfig } from '../hooks/useDashboardConfig';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { Select } from '../components/Select';
import { ConfigPanel } from '../components/ConfigPanel';
import { showToast } from '../components/Toast';
import { api } from '../lib/api';
import type { Settings, N8nWorkflow, LLMModel } from '../types';
import type { DashboardConfig } from '../hooks/useDashboardConfig';
import { CheckCircle, XCircle, Loader2, Cpu, Workflow, Server, Mail, Rocket, Shield, Palette, AlertTriangle } from 'lucide-react';

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

const TABS = [
  { id: 'customize', label: 'Customize', icon: Palette },
  { id: 'llm', label: 'LLM', icon: Cpu },
  { id: 'n8n', label: 'n8n', icon: Workflow },
  { id: 's4hana', label: 'Mock S/4', icon: Server },
  { id: 'email', label: 'Email', icon: Mail },
  { id: 'auth', label: 'Auth', icon: Shield },
  { id: 'deployment', label: 'Deploy', icon: Rocket },
  { id: 'danger', label: 'Danger Zone', icon: AlertTriangle },
] as const;

type TabId = typeof TABS[number]['id'];

export function SettingsPage() {
  const { settings, setSettings, loading, saving, saveSettings, testConnection, sendTestEmail, fetchN8nWorkflows, fetchLlmModels } = useSettings();
  const { config: dashConfig, loading: dashConfigLoading, saving: dashConfigSaving, updateConfig: updateDashConfig, resetConfig: resetDashConfig } = useDashboardConfig();
  const [testStatuses, setTestStatuses] = useState<Record<string, TestStatus>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<TabId>('customize');
  const [configPanelOpen, setConfigPanelOpen] = useState(false);

  // Dynamic dropdown state
  const [n8nWorkflows, setN8nWorkflows] = useState<N8nWorkflow[]>([]);
  const [llmModels, setLlmModels] = useState<LLMModel[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);

  // Danger zone state
  const [resetTargets, setResetTargets] = useState<Set<string>>(new Set());
  const [resetPurpose, setResetPurpose] = useState('');
  const [resetConfirmation, setResetConfirmation] = useState('');
  const [resetting, setResetting] = useState(false);
  const [resetResult, setResetResult] = useState<any>(null);

  const RESET_TARGETS = [
    { value: 'audit_log', label: 'Audit Log', description: 'Clear all audit events (reset events are always preserved)' },
    { value: 'agent_logs', label: 'Agent Invocation Logs', description: 'Delete all stored agent interaction logs' },
    { value: 'sync_history', label: 'Sync Execution History', description: 'Clear the sync run history' },
    { value: 'sessions', label: 'User Sessions', description: 'Force logout all users (you will need to login again)' },
    { value: 'settings', label: 'Settings (Except Auth)', description: 'Reset all settings to defaults (auth/IAS config preserved)' },
  ];

  const handleResetApp = async () => {
    setResetting(true);
    setResetResult(null);
    const res = await api.post<any>('/api/settings/reset-app', {
      confirmation: resetConfirmation,
      purpose: resetPurpose,
      targets: [...resetTargets],
    });
    if (res.ok && res.data && !res.data.error) {
      setResetResult(res.data.results);
      setResetTargets(new Set());
      setResetPurpose('');
      setResetConfirmation('');
      showToast('info', 'App reset completed. Check audit log for permanent record.');
    } else {
      showToast('error', res.data?.detail || res.data?.error || res.error || 'Reset failed');
    }
    setResetting(false);
  };

  // Auto-load models when LLM tab is active
  useEffect(() => {
    if (activeTab === 'llm' && !loading) {
      handleLoadModels();
    }
  }, [activeTab, loading]);

  // Auto-load workflows when n8n tab is active
  useEffect(() => {
    if (activeTab === 'n8n' && !loading) {
      handleLoadWorkflows();
    }
  }, [activeTab, loading]);

  const handleSave = async () => {
    await saveSettings(settings);
  };

  const handleTest = async (type: 'llm' | 'n8n' | 's4hana' | 'email') => {
    setTestStatuses((s) => ({ ...s, [type]: 'testing' }));
    setTestMessages((s) => ({ ...s, [type]: '' }));
    const res = await testConnection(type);
    if (res.ok && res.data) {
      const data = res.data as any;
      const isSuccess = data.success === true || data.status === 'connected' || data.status === 'ok';
      if (isSuccess) {
        setTestStatuses((s) => ({ ...s, [type]: 'success' }));
        setTestMessages((s) => ({ ...s, [type]: data.message || data.status || 'Connected!' }));
      } else {
        setTestStatuses((s) => ({ ...s, [type]: 'error' }));
        setTestMessages((s) => ({ ...s, [type]: data.message || data.error || 'Connection failed' }));
      }
    } else {
      setTestStatuses((s) => ({ ...s, [type]: 'error' }));
      setTestMessages((s) => ({ ...s, [type]: res.error || 'Failed to connect' }));
    }
  };

  const handleLoadWorkflows = async () => {
    setLoadingWorkflows(true);
    const res = await fetchN8nWorkflows();
    if (res.ok && res.data) {
      const data = res.data as any;
      if (data.workflows) {
        setN8nWorkflows(data.workflows);
        setTestMessages((s) => ({ ...s, n8nWorkflows: '' }));
      } else if (data.error) {
        setTestMessages((s) => ({ ...s, n8nWorkflows: data.error }));
      }
    } else {
      setTestMessages((s) => ({ ...s, n8nWorkflows: res.error || 'Failed to load' }));
    }
    setLoadingWorkflows(false);
  };

  const handleLoadModels = async () => {
    setLoadingModels(true);
    const res = await fetchLlmModels();
    if (res.ok && res.data) {
      const data = res.data as any;
      if (data.models) {
        setLlmModels(data.models);
        setTestMessages((s) => ({ ...s, llmModels: '' }));
      } else if (data.error) {
        setTestMessages((s) => ({ ...s, llmModels: data.error }));
      }
    } else {
      setTestMessages((s) => ({ ...s, llmModels: res.error || 'Failed to load' }));
    }
    setLoadingModels(false);
  };

  const update = <K extends keyof Settings>(section: K, updates: Partial<Settings[K]>) => {
    setSettings((prev: Settings) => ({
      ...prev,
      [section]: { ...prev[section], ...updates },
    }));
  };

  const TestIndicator = ({ type }: { type: string }) => {
    const status = testStatuses[type];
    const msg = testMessages[type];
    if (!status || status === 'idle') return null;
    return (
      <div className="flex items-center gap-2 mt-2 text-xs">
        {status === 'testing' && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
        {status === 'success' && <CheckCircle className="h-3 w-3 text-emerald-500" />}
        {status === 'error' && <XCircle className="h-3 w-3 text-red-500" />}
        <span className={status === 'error' ? 'text-red-500' : status === 'success' ? 'text-emerald-500' : ''}>
          {msg || (status === 'testing' ? 'Testing...' : '')}
        </span>
      </div>
    );
  };

  return (
    <div className="max-w-4xl w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure connections and deployment options. All settings are persisted to the backend.
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-border mb-6 overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap flex-shrink-0 ${
                activeTab === tab.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="space-y-6">

      {/* Customization */}
      {activeTab === 'customize' && (
        <div className="space-y-4">
          <Card title="Dashboard Customization" description="Configure dashboard cards, layout, and display preferences">
            <div className="space-y-4">
              <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
                <p>Only administrators can modify these settings. Changes affect all dashboard users.</p>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setConfigPanelOpen(true)}
                loading={dashConfigLoading}
              >
                Open Customization Panel
              </Button>
            </div>
          </Card>

          <Card title="Error Breakdown Limit" description="Maximum number of error categories shown on the dashboard">
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium block mb-1.5">Max Categories</label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={dashConfig.errorBreakdownLimit || 5}
                  onChange={(e) => {
                    const newLimit = Math.max(1, parseInt(e.target.value) || 5);
                    updateDashConfig({ ...dashConfig, errorBreakdownLimit: newLimit });
                  }}
                  className="w-full max-w-[200px] rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                If there are more error categories than this limit, a "View All Errors" link will appear on the dashboard.
              </p>
            </div>
          </Card>

          <ConfigPanel
            config={dashConfig}
            open={configPanelOpen}
            onClose={() => setConfigPanelOpen(false)}
            onSave={async (newConfig: DashboardConfig) => {
              await updateDashConfig(newConfig);
              setConfigPanelOpen(false);
            }}
            onReset={async () => {
              await resetDashConfig();
              setConfigPanelOpen(false);
            }}
            saving={dashConfigSaving}
          />

          <Card title="Theme" description="Application appearance">
            <div className="space-y-3">
              <div className="flex gap-3">
                {(['light', 'dark', 'system'] as const).map((mode) => (
                  <label key={mode} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="theme-mode"
                      value={mode}
                      checked={
                        mode === 'system' ? !localStorage.getItem('theme') :
                        mode === 'dark' ? localStorage.getItem('theme') === 'dark' :
                        localStorage.getItem('theme') === 'light'
                      }
                      onChange={() => {
                        if (mode === 'system') {
                          localStorage.removeItem('theme');
                          const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                          document.documentElement.classList.toggle('dark', prefersDark);
                        } else if (mode === 'dark') {
                          localStorage.setItem('theme', 'dark');
                          document.documentElement.classList.add('dark');
                        } else {
                          localStorage.setItem('theme', 'light');
                          document.documentElement.classList.remove('dark');
                        }
                      }}
                      className="h-4 w-4 text-primary"
                    />
                    <span className="text-sm capitalize">{mode}</span>
                  </label>
                ))}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* LLM Configuration */}
      {activeTab === 'llm' && (
      <Card title="LLM Configuration" description="Configure the language model provider">
        <div className="space-y-4">
          <Select
            label="Provider"
            value={settings.llm.provider}
            onChange={(e) => update('llm', { provider: e.target.value as Settings['llm']['provider'] })}
            options={[
              { value: 'local-proxy', label: 'Local Proxy (LiteLLM)' },
              { value: 'sap-ai-core', label: 'SAP AI Core' },
            ]}
          />
          <Input
            label="Base URL"
            value={settings.llm.baseUrl}
            onChange={(e) => update('llm', { baseUrl: e.target.value })}
            placeholder="http://localhost:6655/litellm/v1"
          />
          <Input
            label="API Key"
            type="password"
            value={settings.llm.apiKey}
            onChange={(e) => {
              const newKey = e.target.value;
              update('llm', { apiKey: newKey });
              // Auto-load models when key is entered (debounced)
              if (newKey && newKey.length > 3 && !newKey.startsWith('*')) {
                clearTimeout((window as any).__llmModelTimer);
                (window as any).__llmModelTimer = setTimeout(async () => {
                  setLoadingModels(true);
                  const updatedSettings = { ...settings, llm: { ...settings.llm, apiKey: newKey } };
                  const res = await fetchLlmModels(updatedSettings);
                  if (res.ok && res.data) {
                    const data = res.data as any;
                    if (data.models) {
                      setLlmModels(data.models);
                      setTestMessages((s) => ({ ...s, llmModels: '' }));
                    } else {
                      setTestMessages((s) => ({ ...s, llmModels: data.detail || data.error || 'Failed' }));
                    }
                  } else {
                    setTestMessages((s) => ({ ...s, llmModels: res.error || 'Failed to fetch models' }));
                  }
                  setLoadingModels(false);
                }, 800);
              }
            }}
            placeholder="Enter API key to auto-load models..."
          />
          <div>
            {loadingModels ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading models...
              </div>
            ) : (
              <Select
                label="Model"
                value={settings.llm.model}
                onChange={(e) => update('llm', { model: e.target.value })}
                options={[
                  { value: '', label: llmModels.length === 0 ? '-- Enter API key to load models --' : '-- Select a model --' },
                  ...llmModels.map((m) => ({ value: m.id, label: m.name })),
                ]}
              />
            )}
            {testMessages.llmModels && (
              <p className="text-xs text-red-500 mt-1">{testMessages.llmModels}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTest('llm')}
              loading={testStatuses.llm === 'testing'}
            >
              Test Connection
            </Button>
            <TestIndicator type="llm" />
          </div>
        </div>
      </Card>
      )}

      {/* n8n Connection */}
      {activeTab === 'n8n' && (
      <Card title="n8n Connection" description="Configure the n8n workflow automation platform">
        <div className="space-y-4">
          <Input
            label="n8n URL"
            value={settings.n8n.url}
            onChange={(e) => update('n8n', { url: e.target.value })}
            placeholder="http://localhost:5678"
          />
          <Input
            label="API Key"
            type="password"
            value={settings.n8n.apiKey}
            onChange={(e) => {
              const newKey = e.target.value;
              update('n8n', { apiKey: newKey });
              // Auto-load workflows when key is entered
              if (newKey && newKey.length > 5 && !newKey.startsWith('*')) {
                clearTimeout((window as any).__n8nWfTimer);
                (window as any).__n8nWfTimer = setTimeout(async () => {
                  setLoadingWorkflows(true);
                  const updatedSettings = { ...settings, n8n: { ...settings.n8n, apiKey: newKey } };
                  const res = await fetchN8nWorkflows(updatedSettings);
                  if (res.ok && res.data) {
                    const data = res.data as any;
                    if (data.workflows) {
                      setN8nWorkflows(data.workflows);
                      setTestMessages((s) => ({ ...s, n8nWorkflows: '' }));
                    } else {
                      setTestMessages((s) => ({ ...s, n8nWorkflows: data.detail || data.error || 'Failed' }));
                    }
                  } else {
                    setTestMessages((s) => ({ ...s, n8nWorkflows: res.error || 'Failed to fetch workflows' }));
                  }
                  setLoadingWorkflows(false);
                }, 800);
              }
            }}
            placeholder="Enter API key to auto-load workflows..."
          />
          <div>
            {loadingWorkflows ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading workflows...
              </div>
            ) : (
              <div className="space-y-3">
                <Select
                  label="Main Sync Workflow"
                  value={settings.n8n.workflowId}
                  onChange={(e) => update('n8n', { workflowId: e.target.value })}
                  options={[
                    { value: '', label: n8nWorkflows.length === 0 ? '-- Enter API key to load --' : '-- Select main sync workflow --' },
                    ...n8nWorkflows.map((w) => ({ value: w.id, label: `${w.name} (${w.id})${w.active ? '' : ' [inactive]'}` })),
                  ]}
                />
                <Select
                  label="Retry Sync Workflow"
                  value={settings.n8n.retryWorkflowId}
                  onChange={(e) => update('n8n', { retryWorkflowId: e.target.value })}
                  options={[
                    { value: '', label: n8nWorkflows.length === 0 ? '-- Enter API key to load --' : '-- Select retry workflow --' },
                    ...n8nWorkflows.map((w) => ({ value: w.id, label: `${w.name} (${w.id})${w.active ? '' : ' [inactive]'}` })),
                  ]}
                />
                <Select
                  label="Agent Fix Workflow"
                  value={settings.n8n.agentFixWorkflowId}
                  onChange={(e) => update('n8n', { agentFixWorkflowId: e.target.value })}
                  options={[
                    { value: '', label: n8nWorkflows.length === 0 ? '-- Enter API key to load --' : '-- Select agent fix workflow --' },
                    ...n8nWorkflows.map((w) => ({ value: w.id, label: `${w.name} (${w.id})${w.active ? '' : ' [inactive]'}` })),
                  ]}
                />
                <div>
                  <label className="text-sm font-medium block mb-1.5">Monitor Workflows (multi-select)</label>
                  <div className="space-y-1 max-h-40 overflow-y-auto border border-border rounded-md p-2">
                    {n8nWorkflows.length === 0 ? (
                      <p className="text-xs text-muted-foreground">Enter API key to load workflows</p>
                    ) : (
                      n8nWorkflows.map((w) => (
                        <label key={w.id} className="flex items-center gap-2 text-xs cursor-pointer py-0.5">
                          <input
                            type="checkbox"
                            checked={settings.n8n.monitoredWorkflowIds.includes(w.id)}
                            onChange={(e) => {
                              const current = settings.n8n.monitoredWorkflowIds || [];
                              const next = e.target.checked
                                ? [...current, w.id]
                                : current.filter((id: string) => id !== w.id);
                              update('n8n', { monitoredWorkflowIds: next });
                            }}
                            className="h-3 w-3"
                          />
                          {w.name} ({w.id}){w.active ? '' : ' [inactive]'}
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Only selected workflows will appear in the Workflows monitor page.</p>
                </div>
              </div>
            )}
            {testMessages.n8nWorkflows && (
              <p className="text-xs text-red-500 mt-1">{testMessages.n8nWorkflows}</p>
            )}
          </div>
          <Input
            label="Webhook Base URL (optional)"
            value={settings.n8n.webhookUrl || ''}
            onChange={(e) => update('n8n', { webhookUrl: e.target.value })}
            placeholder="e.g. https://your-tunnel.ngrok-free.app"
          />
          <p className="text-xs text-muted-foreground">
            If n8n is behind a tunnel (ngrok, cloudflare), enter the public base URL here. Leave empty to use the n8n URL above.
          </p>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTest('n8n')}
              loading={testStatuses.n8n === 'testing'}
            >
              Test Connection
            </Button>
            <TestIndicator type="n8n" />
          </div>
        </div>
      </Card>
      )}

      {/* Mock S/4HANA */}
      {activeTab === 's4hana' && (
      <Card title="Mock S/4HANA" description="Configure the mock SAP S/4HANA server">
        <div className="space-y-4">
          <Input
            label="Server URL"
            value={settings.mockS4hana.serverUrl}
            onChange={(e) => update('mockS4hana', { serverUrl: e.target.value })}
            placeholder="http://localhost:8090"
          />
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTest('s4hana')}
              loading={testStatuses.s4hana === 'testing'}
            >
              Test Connection
            </Button>
            <TestIndicator type="s4hana" />
          </div>
        </div>
      </Card>
      )}

      {/* Deployment Mode */}
      {activeTab === 'deployment' && (
      <Card title="Deployment Mode" description="Select how this stack is deployed">
        <div className="space-y-4">
          <div className="flex gap-4">
            {(['local', 'docker', 'production'] as const).map((mode) => (
              <label key={mode} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="deployment-mode"
                  value={mode}
                  checked={settings.deployment.mode === mode}
                  onChange={() => update('deployment', { mode })}
                  className="h-4 w-4 text-primary"
                />
                <span className="text-sm capitalize">{mode}</span>
              </label>
            ))}
          </div>
          <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
            {settings.deployment.mode === 'local' && (
              <p>Running all services locally. Ensure n8n, LiteLLM proxy, and mock-s4hana are started.</p>
            )}
            {settings.deployment.mode === 'docker' && (
              <p>Running via Docker Compose. Services communicate via Docker network. Use service names as hosts.</p>
            )}
            {settings.deployment.mode === 'production' && (
              <p>Production deployment. Ensure all endpoints use HTTPS and proper authentication is configured.</p>
            )}
          </div>
        </div>
      </Card>
      )}

      {/* Email/SMTP */}
      {activeTab === 'email' && (
      <Card title="Email / SMTP (Optional)" description="Configure email notifications">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="SMTP Host"
              value={settings.email.smtpHost}
              onChange={(e) => update('email', { smtpHost: e.target.value })}
              placeholder="smtp.example.com"
            />
            <Input
              label="SMTP Port"
              type="number"
              value={settings.email.smtpPort || ''}
              onChange={(e) => update('email', { smtpPort: parseInt(e.target.value) || 587 })}
              placeholder="587"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Username"
              value={settings.email.username}
              onChange={(e) => update('email', { username: e.target.value })}
              placeholder="user@example.com"
            />
            <Input
              label="Password"
              type="password"
              value={settings.email.password}
              onChange={(e) => update('email', { password: e.target.value })}
              placeholder="••••••••"
            />
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTest('email')}
              loading={testStatuses.email === 'testing'}
            >
              Test Connection
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                setTestStatuses((s) => ({ ...s, emailSend: 'testing' }));
                setTestMessages((s) => ({ ...s, emailSend: '' }));
                const res = await sendTestEmail();
                if (res.ok && res.data) {
                  const data = res.data as any;
                  if (data.status === 'sent') {
                    setTestStatuses((s) => ({ ...s, emailSend: 'success' }));
                    setTestMessages((s) => ({ ...s, emailSend: data.message || 'Email sent! Check Mailpit at http://localhost:8025' }));
                  } else {
                    setTestStatuses((s) => ({ ...s, emailSend: 'error' }));
                    setTestMessages((s) => ({ ...s, emailSend: data.error || 'Failed to send' }));
                  }
                } else {
                  setTestStatuses((s) => ({ ...s, emailSend: 'error' }));
                  setTestMessages((s) => ({ ...s, emailSend: res.error || 'Failed' }));
                }
              }}
              loading={testStatuses.emailSend === 'testing'}
            >
              Send Test Email
            </Button>
            <TestIndicator type="email" />
            <TestIndicator type="emailSend" />
          </div>
        </div>
      </Card>
      )}

      {/* Auth / SAP IAS */}
      {activeTab === 'auth' && (
      <Card title="Authentication (SAP IAS)" description="Configure SAP Identity Authentication Service for SSO. Leave empty for anonymous local development.">
        <div className="space-y-4">
          <Input
            label="IAS Tenant URL"
            value={settings.auth.iasUrl}
            onChange={(e) => update('auth', { iasUrl: e.target.value })}
            placeholder="https://mytenant.accounts.ondemand.com"
          />
          <p className="text-xs text-muted-foreground">
            The base URL of your SAP IAS tenant. Found in BTP cockpit under Security &rarr; Trust Configuration.
          </p>
          <Input
            label="Client ID"
            value={settings.auth.clientId}
            onChange={(e) => update('auth', { clientId: e.target.value })}
            placeholder="OIDC application client ID"
          />
          <Input
            label="Client Secret"
            type="password"
            value={settings.auth.clientSecret}
            onChange={(e) => update('auth', { clientSecret: e.target.value })}
            placeholder="••••••••"
          />
          <div className="rounded-md bg-muted p-3 text-xs text-muted-foreground space-y-1">
            <p><strong>Note:</strong> Authentication is optional. If IAS is not configured, the dashboard works in anonymous mode.</p>
            <p>When configured, users will be redirected to IAS for login. The redirect URI is derived automatically from the request origin (no manual configuration needed). Register all access URLs in your IAS application settings (e.g. <code>http://localhost:3001/api/auth/callback</code>, <code>http://your-ip:3001/api/auth/callback</code>).</p>
          </div>
        </div>
      </Card>
      )}

      {/* Danger Zone */}
      {activeTab === 'danger' && (
        <div className="space-y-6">
          <div className="rounded-lg border-2 border-red-500/30 bg-red-500/5 p-6">
            <h3 className="text-lg font-semibold text-red-600 dark:text-red-400 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Danger Zone
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              These actions are destructive and cannot be undone. A permanent audit record will be created.
            </p>

            <div className="mt-6 space-y-4">
              <p className="text-sm font-medium">Select items to reset:</p>

              {/* Selectable reset targets */}
              <div className="space-y-2">
                {RESET_TARGETS.map((target) => (
                  <label key={target.value} className="flex items-start gap-3 p-3 rounded-md border border-border hover:border-red-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={resetTargets.has(target.value)}
                      onChange={(e) => {
                        const next = new Set(resetTargets);
                        if (e.target.checked) next.add(target.value);
                        else next.delete(target.value);
                        setResetTargets(next);
                      }}
                      className="h-4 w-4 mt-0.5"
                    />
                    <div>
                      <span className="text-sm font-medium">{target.label}</span>
                      <p className="text-xs text-muted-foreground">{target.description}</p>
                    </div>
                  </label>
                ))}
              </div>

              {/* Purpose */}
              <div>
                <label className="text-sm font-medium block mb-1">Reason for reset</label>
                <textarea
                  value={resetPurpose}
                  onChange={(e) => setResetPurpose(e.target.value)}
                  placeholder="Explain why you are resetting the app (minimum 10 characters)..."
                  rows={2}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>

              {/* Confirmation */}
              <div>
                <label className="text-sm font-medium block mb-1">
                  Type <code className="px-1 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-600 rounded text-xs">DELETE</code> to confirm
                </label>
                <input
                  type="text"
                  value={resetConfirmation}
                  onChange={(e) => setResetConfirmation(e.target.value)}
                  placeholder="DELETE"
                  className="w-full max-w-xs rounded-md border border-red-300 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>

              {/* Reset button */}
              <button
                onClick={handleResetApp}
                disabled={
                  resetConfirmation !== 'DELETE' ||
                  resetTargets.size === 0 ||
                  resetPurpose.length < 10 ||
                  resetting
                }
                className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {resetting ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertTriangle className="h-4 w-4" />}
                Reset App
              </button>

              {resetResult && (
                <div className="mt-4 rounded-md border border-border bg-muted/50 p-4">
                  <p className="text-sm font-medium text-emerald-600 mb-2">Reset completed</p>
                  <pre className="text-xs text-muted-foreground overflow-auto">
                    {JSON.stringify(resetResult, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      </div>

      {/* Save */}
      <div className="flex justify-end pt-4 border-t border-border mt-6">
        <Button onClick={handleSave} loading={saving} size="lg">
          Save Settings
        </Button>
      </div>
    </div>
  );
}
