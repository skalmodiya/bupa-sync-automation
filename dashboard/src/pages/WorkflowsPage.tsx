import { useEffect, useState } from 'react';
import { useN8n } from '../hooks/useN8n';
import { useSettings } from '../hooks/useSettings';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { DataTable, type Column } from '../components/DataTable';
import { RefreshCw, Play, ExternalLink, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import type { N8nExecution } from '../types';

export function WorkflowsPage() {
  const { settings } = useSettings();
  const { executions, loading, error, fetchExecutions, triggerSync } = useN8n();
  const [triggering, setTriggering] = useState(false);
  const [triggerStatus, setTriggerStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [triggerMessage, setTriggerMessage] = useState('');
  const [isPolling, setIsPolling] = useState(true);
  const [pollInterval, setPollInterval] = useState(5);
  const [lastRefresh, setLastRefresh] = useState<string>('');

  // Initial fetch
  useEffect(() => {
    fetchExecutions();
  }, [fetchExecutions]);

  // Silent auto-poll (does NOT set loading state to avoid flicker)
  useEffect(() => {
    if (!isPolling) return;
    const interval = setInterval(() => {
      fetchExecutions();
      setLastRefresh(new Date().toLocaleTimeString());
    }, pollInterval * 1000);
    return () => clearInterval(interval);
  }, [fetchExecutions, isPolling, pollInterval]);

  // Detect if any execution is currently running
  const hasRunningExecution = executions.some(
    (e) => e.status === 'running' || e.status === 'waiting' || e.status === 'unknown' || e.finished === false
  );

  const handleTriggerSync = async () => {
    setTriggering(true);
    setTriggerStatus('idle');
    setTriggerMessage('');
    const success = await triggerSync();
    if (success) {
      setTriggerStatus('success');
      setTriggerMessage('Workflow triggered successfully! Refreshing executions...');
      setTimeout(() => fetchExecutions(), 1000);
      setTimeout(() => fetchExecutions(), 3000);
      setTimeout(() => fetchExecutions(), 8000);
    } else {
      setTriggerStatus('error');
      setTriggerMessage('Failed to trigger workflow. Make sure it is active in n8n or open in editor with "Listen for test event".');
    }
    setTriggering(false);
  };

  const formatDuration = (exec: N8nExecution) => {
    if (!exec.startedAt || !exec.stoppedAt) return '—';
    const start = new Date(exec.startedAt).getTime();
    const end = new Date(exec.stoppedAt).getTime();
    const ms = end - start;
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  };

  const formatTime = (iso: string) => {
    return new Date(iso).toLocaleString();
  };

  const getStatusType = (status: string) => {
    switch (status) {
      case 'success': return 'success' as const;
      case 'error': return 'error' as const;
      case 'running': case 'waiting': return 'running' as const;
      default: return 'warning' as const;
    }
  };

  const columns: Column<N8nExecution>[] = [
    {
      key: 'id',
      label: 'ID',
      sortable: true,
      filterable: true,
      filterType: 'text',
      render: (val) => <span className="font-mono text-xs">{val}</span>,
    },
    {
      key: 'workflowId',
      label: 'Workflow ID',
      sortable: true,
      filterable: true,
      filterType: 'text',
      render: (val) => <span className="font-mono text-xs">{val || '—'}</span>,
    },
    {
      key: 'workflowName',
      label: 'Workflow Name',
      sortable: true,
      filterable: true,
      filterType: 'text',
      render: (val, row) => <span className="text-sm">{val || `Workflow #${row.workflowId}`}</span>,
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      filterable: true,
      filterType: 'dropdown',
      filterOptions: [
        { value: 'success', label: 'Success' },
        { value: 'error', label: 'Error' },
        { value: 'running', label: 'Running' },
        { value: 'waiting', label: 'Waiting' },
      ],
      render: (val) => (
        <StatusBadge
          status={getStatusType(val)}
          label={val}
          pulse={val === 'running'}
        />
      ),
    },
    {
      key: 'startedAt',
      label: 'Started At',
      sortable: true,
      render: (val) => <span className="text-muted-foreground text-xs">{val ? formatTime(val) : '—'}</span>,
    },
    {
      key: 'stoppedAt',
      label: 'Duration',
      sortable: true,
      render: (_val, row) => <span className="text-muted-foreground text-xs">{formatDuration(row)}</span>,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Workflow Monitor</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Monitor n8n workflow executions and trigger sync operations
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={() => fetchExecutions()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={handleTriggerSync} loading={triggering}>
            <Play className="h-4 w-4" />
            Trigger Sync
          </Button>
          <a
            href={settings.n8n.workflowId
              ? `/n8n/workflow/${settings.n8n.workflowId}`
              : '/n8n/'}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            Open in n8n
          </a>
        </div>
      </div>

      {/* Polling Controls */}
      <div className="flex items-center justify-between text-xs text-muted-foreground bg-muted/30 rounded-md px-3 py-2 border border-border">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isPolling}
              onChange={(e) => setIsPolling(e.target.checked)}
              className="h-3 w-3"
            />
            Auto-refresh
          </label>
          {isPolling && (
            <label className="flex items-center gap-1">
              every
              <select
                value={pollInterval}
                onChange={(e) => setPollInterval(Number(e.target.value))}
                className="bg-background border border-border rounded px-1 py-0.5 text-xs"
              >
                <option value={3}>3s</option>
                <option value={5}>5s</option>
                <option value={10}>10s</option>
                <option value={30}>30s</option>
                <option value={60}>60s</option>
              </select>
            </label>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isPolling && <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />}
          {lastRefresh && <span>Last: {lastRefresh}</span>}
          <span>{executions.length} execution{executions.length !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Live Execution Status */}
      {hasRunningExecution && (
        <div className="flex items-center gap-2 p-3 rounded-md text-sm bg-blue-500/10 text-blue-600 border border-blue-500/20">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="font-medium">Workflow is currently running...</span>
          <span className="text-xs text-blue-500 ml-auto">Auto-refreshing every {pollInterval}s</span>
        </div>
      )}

      {/* Trigger Status Banner */}
      {triggerStatus !== 'idle' && (
        <div className={`flex items-center gap-2 p-3 rounded-md text-sm ${
          triggerStatus === 'success' ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20' :
          'bg-red-500/10 text-red-600 border border-red-500/20'
        }`}>
          {triggerStatus === 'success' ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
          {triggerMessage}
          {triggerStatus === 'success' && <Loader2 className="h-3 w-3 animate-spin ml-auto" />}
        </div>
      )}

      {/* Executions Table */}
      <Card title={`Recent Executions (${executions.length})`} description="Latest workflow execution history">
        {error && (
          <div className="mb-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {!settings.n8n.apiKey && (
          <div className="rounded-md bg-muted p-4 text-sm text-muted-foreground text-center">
            Configure your n8n API key in Settings to view executions.
          </div>
        )}

        {settings.n8n.apiKey && (
          <DataTable<N8nExecution>
            columns={columns}
            data={executions}
            loading={loading}
            rowKey={(row) => row.id}
            expandable
            renderExpanded={(row) => (
              <div className="rounded-md bg-muted p-3">
                <p className="text-xs font-medium mb-2">Execution Details</p>
                <pre className="text-xs text-muted-foreground overflow-auto max-h-40">
                  {JSON.stringify(
                    {
                      id: row.id,
                      mode: row.mode,
                      finished: row.finished,
                      startedAt: row.startedAt,
                      stoppedAt: row.stoppedAt,
                    },
                    null,
                    2
                  )}
                </pre>
              </div>
            )}
            emptyMessage="No executions found."
          />
        )}
      </Card>
    </div>
  );
}
