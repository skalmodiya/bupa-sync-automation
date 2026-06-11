import { useEffect, useState, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { clsx } from 'clsx';
import { Loader2, ChevronDown, ChevronRight, Bot, RefreshCw, RotateCcw, X } from 'lucide-react';
import { showToast } from '../components/Toast';

interface SyncRecord {
  pernr: string;
  name: string;
  status: 'synced' | 'failed' | 'pending';
  error_type: string;
  error_message: string;
  bp_id: string;
  org_unit: string;
}

interface RecordsResponse {
  records: SyncRecord[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  error?: string;
}

interface RetryResponse {
  status: string;
  pernr_count: number;
  mode: string;
  result: unknown;
  error?: string;
}

interface AgentFixResponse {
  status: string;
  pernr_count: number;
  errors_analyzed: number;
  agent_response: string;
  error?: string;
}

type StatusFilter = 'all' | 'synced' | 'failed' | 'pending';

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'synced', label: 'Synced' },
  { value: 'failed', label: 'Failed' },
  { value: 'pending', label: 'Pending' },
];

const BATCH_SIZES = [10, 20, 50, 100];

interface ErrorCategory {
  value: string;
  label: string;
  count: number;
}

const STATUS_BADGE_CLASSES: Record<string, string> = {
  synced: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
};

export function RecordsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialStatus = (searchParams.get('status') as StatusFilter) || 'all';
  const initialCategory = searchParams.get('category') || '';

  const [records, setRecords] = useState<SyncRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(initialStatus);
  const [categoryFilter, setCategoryFilter] = useState(initialCategory);
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(
    initialCategory ? new Set([initialCategory]) : new Set()
  );
  const [batchSize, setBatchSize] = useState(10);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  // Category action states
  const [retryCategoryLoading, setRetryCategoryLoading] = useState(false);
  const [agentCategoryLoading, setAgentCategoryLoading] = useState(false);

  // Dynamic error categories from backend
  const [errorCategories, setErrorCategories] = useState<ErrorCategory[]>([]);

  // Fetch error categories on mount and when filter changes to failed
  useEffect(() => {
    if (statusFilter === 'failed' || statusFilter === 'all') {
      api.get<{ categories: ErrorCategory[] }>('/api/sync/error-categories').then((res) => {
        if (res.ok && res.data?.categories) {
          setErrorCategories(res.data.categories);
        }
      });
    }
  }, [statusFilter]);

  // Selection state
  const [selectedPernrs, setSelectedPernrs] = useState<Set<string>>(new Set());

  // Action states
  const [retryLoading, setRetryLoading] = useState(false);
  const [agentLoading, setAgentLoading] = useState(false);
  const [retryAllLoading, setRetryAllLoading] = useState(false);

  // Agent panel state
  const [agentPanelOpen, setAgentPanelOpen] = useState(false);
  const [agentResponse, setAgentResponse] = useState<string>('');

  // Confirm dialog state
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({ open: false, title: '', message: '', onConfirm: () => {} });

  const offsetRef = useRef(0);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Determine if checkboxes should be shown
  const showCheckboxes = statusFilter === 'failed' || statusFilter === 'all';

  // Failed records among currently loaded ones
  const failedRecords = records.filter((r) => r.status === 'failed');
  const selectedFailedPernrs = Array.from(selectedPernrs).filter((p) =>
    failedRecords.some((r) => r.pernr === p)
  );

  const fetchRecords = useCallback(
    async (offset: number, append: boolean = false) => {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }

      const catParam = selectedCategories.size > 0 ? [...selectedCategories].join(',') : categoryFilter;
      const res = await api.get<RecordsResponse>(
        `/api/sync/records?status=${statusFilter}&category=${catParam}&offset=${offset}&limit=${batchSize}`
      );

      if (res.ok && res.data && !res.data.error) {
        if (append) {
          setRecords((prev) => [...prev, ...res.data!.records]);
        } else {
          setRecords(res.data.records);
        }
        setTotal(res.data.total);
        setHasMore(res.data.has_more);
        offsetRef.current = offset + res.data.records.length;
      }

      if (append) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    },
    [statusFilter, categoryFilter, selectedCategories, batchSize]
  );

  // Reset and fetch when filter or batch size changes
  useEffect(() => {
    offsetRef.current = 0;
    setRecords([]);
    setExpandedRow(null);
    setSelectedPernrs(new Set());
    fetchRecords(0, false);
  }, [fetchRecords]);

  // Update URL when filter changes
  useEffect(() => {
    const params: Record<string, string> = {};
    if (statusFilter !== 'all') params.status = statusFilter;
    if (categoryFilter) params.category = categoryFilter;
    setSearchParams(params);
  }, [statusFilter, categoryFilter, setSearchParams]);

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && hasMore && !loadingMore && !loading) {
          fetchRecords(offsetRef.current, true);
        }
      },
      { threshold: 0.1 }
    );

    if (sentinelRef.current) {
      observerRef.current.observe(sentinelRef.current);
    }

    return () => {
      if (observerRef.current) observerRef.current.disconnect();
    };
  }, [hasMore, loadingMore, loading, fetchRecords]);

  const handleFilterChange = (filter: StatusFilter) => {
    setStatusFilter(filter);
  };

  // Selection handlers
  const toggleSelectAll = () => {
    const selectableRecords = records.filter((r) => r.status === 'failed');
    if (selectedPernrs.size === selectableRecords.length && selectableRecords.length > 0) {
      setSelectedPernrs(new Set());
    } else {
      setSelectedPernrs(new Set(selectableRecords.map((r) => r.pernr)));
    }
  };

  const toggleSelect = (pernr: string) => {
    setSelectedPernrs((prev) => {
      const next = new Set(prev);
      if (next.has(pernr)) {
        next.delete(pernr);
      } else {
        next.add(pernr);
      }
      return next;
    });
  };

  // Action: Retry selected
  const handleRetrySelected = async () => {
    if (selectedFailedPernrs.length === 0) {
      showToast('error', 'No failed records selected');
      return;
    }
    setRetryLoading(true);
    const res = await api.post<RetryResponse>('/api/sync/retry', {
      pernr_list: selectedFailedPernrs,
      mode: 'selected',
    });
    setRetryLoading(false);

    if (res.ok && res.data && !res.data.error) {
      showToast('success', `Retry triggered for ${res.data.pernr_count} employees`);
      setSelectedPernrs(new Set());
      offsetRef.current = 0;
      fetchRecords(0, false);
    } else {
      showToast('error', res.data?.error || res.error || 'Retry failed');
    }
  };

  // Action: Retry all failed
  const handleRetryAllFailed = () => {
    const failedCount = statusFilter === 'failed' ? total : failedRecords.length;
    setConfirmDialog({
      open: true,
      title: 'Retry All Failed Records',
      message: `Are you sure you want to retry sync for all failed records${failedCount > 0 ? ` (~${failedCount} records)` : ''}? This will re-attempt the BUPA sync for every record in error state.`,
      onConfirm: async () => {
        setConfirmDialog((prev) => ({ ...prev, open: false }));
        setRetryAllLoading(true);
        const res = await api.post<RetryResponse>('/api/sync/retry', {
          pernr_list: [],
          mode: 'all_failed',
        });
        setRetryAllLoading(false);

        if (res.ok && res.data && !res.data.error) {
          showToast('success', `Retry triggered for ${res.data.pernr_count} failed employees`);
          setSelectedPernrs(new Set());
          offsetRef.current = 0;
          fetchRecords(0, false);
        } else {
          showToast('error', res.data?.error || res.error || 'Retry all failed');
        }
      },
    });
  };

  // Action: Ask Agent to Fix
  const handleAskAgentFix = async () => {
    if (selectedFailedPernrs.length === 0) {
      showToast('error', 'No failed records selected');
      return;
    }
    setAgentLoading(true);
    const res = await api.post<AgentFixResponse>('/api/sync/ask-agent-fix', {
      pernr_list: selectedFailedPernrs,
    });
    setAgentLoading(false);

    if (res.ok && res.data && !res.data.error) {
      setAgentResponse(res.data.agent_response);
      setAgentPanelOpen(true);
      showToast('success', `Agent analyzed ${res.data.errors_analyzed} errors`);
    } else {
      showToast('error', res.data?.error || res.error || 'Agent request failed');
    }
  };

  // Action: Apply & Retry (from agent panel)
  const handleApplyAndRetry = async () => {
    setAgentPanelOpen(false);
    await handleRetrySelected();
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Sync Records</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Showing {statusFilter === 'all' ? 'all' : statusFilter} records
          {total > 0 && ` — ${total} rows`}
          {statusFilter === 'all' && total > 0 && (
            <span className="ml-2 text-xs bg-muted px-2 py-0.5 rounded" title="An employee with multiple errors appears as multiple rows (one per error). Dashboard shows unique employee count (50).">
              Note: Employees with multiple errors appear as separate rows
            </span>
          )}
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          {/* Filter pills */}
          <div className="flex gap-1 rounded-lg bg-muted p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => handleFilterChange(f.value)}
                className={clsx(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                  statusFilter === f.value
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Batch size selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Per batch:</span>
            <select
              value={batchSize}
              onChange={(e) => setBatchSize(parseInt(e.target.value))}
              className="rounded-md border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {BATCH_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
      </div>

        {/* Error Category filter (visible when failed is selected or all) */}
        {(statusFilter === 'failed' || statusFilter === 'all') && (
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground font-medium">Category:</span>
              {errorCategories.map((c) => (
                <label
                  key={c.value}
                  className={clsx(
                    'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs cursor-pointer border transition-colors',
                    selectedCategories.has(c.value)
                      ? 'bg-primary/10 border-primary/30 text-primary font-medium'
                      : 'border-border text-muted-foreground hover:border-primary/20 hover:text-foreground'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedCategories.has(c.value)}
                    onChange={(e) => {
                      const next = new Set(selectedCategories);
                      if (e.target.checked) next.add(c.value);
                      else next.delete(c.value);
                      setSelectedCategories(next);
                      setCategoryFilter(next.size === 1 ? [...next][0] : next.size === 0 ? '' : [...next][0]);
                    }}
                    className="h-3 w-3"
                  />
                  {c.label} ({c.count})
                </label>
              ))}
              {selectedCategories.size > 0 && (
                <button
                  onClick={() => { setSelectedCategories(new Set()); setCategoryFilter(''); }}
                  className="text-xs text-muted-foreground hover:text-foreground ml-1"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {/* Category-level actions */}
            {selectedCategories.size > 0 && (
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-xs text-muted-foreground">
                  {selectedCategories.size} categor{selectedCategories.size > 1 ? 'ies' : 'y'}:
                </span>
                <button
                  onClick={async () => {
                    setAgentCategoryLoading(true);
                    const res = await api.post<AgentFixResponse>('/api/sync/ask-agent-fix', {
                      categories: [...selectedCategories],
                      mode: 'by_category',
                    });
                    if (res.ok && res.data && !res.data.error) {
                      setAgentResponse(res.data.agent_response);
                      setAgentPanelOpen(true);
                      showToast('success', `Agent analyzed ${res.data.errors_analyzed} errors`);
                    } else {
                      showToast('error', res.data?.error || res.error || 'Agent fix failed');
                    }
                    setAgentCategoryLoading(false);
                  }}
                  disabled={agentCategoryLoading}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {agentCategoryLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Bot className="h-3 w-3" />}
                  Fix Category
                </button>
                <button
                  onClick={async () => {
                    if (!window.confirm(`Retry sync for all records in ${selectedCategories.size} selected categor${selectedCategories.size > 1 ? 'ies' : 'y'}?`)) return;
                    setRetryCategoryLoading(true);
                    const res = await api.post<RetryResponse>('/api/sync/retry', {
                      categories: [...selectedCategories],
                      mode: 'by_category',
                    });
                    if (res.ok && res.data && !res.data.error) {
                      showToast('success', `Retry triggered for ${res.data.pernr_count} employees`);
                      fetchRecords(0, false);
                    } else {
                      showToast('error', res.data?.error || res.error || 'Retry failed');
                    }
                    setRetryCategoryLoading(false);
                  }}
                  disabled={retryCategoryLoading}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {retryCategoryLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                  Retry Category
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Bar - shown when records are selected or viewing failed */}
      {showCheckboxes && (selectedPernrs.size > 0 || statusFilter === 'failed') && (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/50 px-4 py-3">
          {selectedPernrs.size > 0 && (
            <span className="text-sm font-medium text-foreground">
              {selectedFailedPernrs.length} record{selectedFailedPernrs.length !== 1 ? 's' : ''} selected
            </span>
          )}

          <div className="flex items-center gap-2 ml-auto">
            {/* Ask Agent to Fix */}
            <button
              onClick={handleAskAgentFix}
              disabled={agentLoading || selectedFailedPernrs.length === 0}
              className={clsx(
                'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                'bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {agentLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Bot className="h-4 w-4" />
              )}
              Ask Agent to Fix
            </button>

            {/* Retry Selected */}
            <button
              onClick={handleRetrySelected}
              disabled={retryLoading || selectedFailedPernrs.length === 0}
              className={clsx(
                'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {retryLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Retry Sync
            </button>

            {/* Retry All Failed */}
            <button
              onClick={handleRetryAllFailed}
              disabled={retryAllLoading}
              className={clsx(
                'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                'bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {retryAllLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
              Retry All Failed
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : records.length === 0 ? (
        <div className="flex items-center justify-center h-64 text-sm text-muted-foreground">
          No records found for the selected filter.
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden flex flex-col max-h-[calc(100vh-320px)]">
          <div className="overflow-auto flex-1">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-muted/95 backdrop-blur-sm">
              <tr className="border-b border-border bg-muted/50">
                {showCheckboxes && (
                  <th className="px-3 py-3 text-left w-10">
                    <input
                      type="checkbox"
                      checked={
                        failedRecords.length > 0 &&
                        selectedPernrs.size === failedRecords.length
                      }
                      onChange={toggleSelectAll}
                      className="h-4 w-4 rounded border-border text-blue-600 focus:ring-blue-500"
                      title="Select all failed records"
                    />
                  </th>
                )}
                <th className="px-4 py-3 text-left font-medium text-muted-foreground w-8" />
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">PERNR</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Error Type</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Error Message</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">BP ID</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Org Unit</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => {
                const isExpanded = expandedRow === record.pernr;
                return (
                  <RecordRow
                    key={record.pernr}
                    record={record}
                    isExpanded={isExpanded}
                    isSelected={selectedPernrs.has(record.pernr)}
                    showCheckboxColumn={showCheckboxes}
                    isSelectable={record.status === 'failed'}
                    onToggle={() =>
                      setExpandedRow(isExpanded ? null : record.pernr)
                    }
                    onSelect={() => toggleSelect(record.pernr)}
                  />
                );
              })}
            </tbody>
          </table>

          {/* Sentinel for infinite scroll */}
          <div ref={sentinelRef} className="h-1" />

          {/* Loading more indicator */}
          {loadingMore && (
            <div className="flex items-center justify-center gap-2 py-4 border-t border-border">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Loading more...</span>
            </div>
          )}

          {/* All loaded indicator */}
          {!hasMore && records.length > 0 && !loadingMore && (
            <div className="flex items-center justify-center py-4 border-t border-border">
              <span className="text-sm text-muted-foreground">
                All {total} records loaded
              </span>
            </div>
          )}
          </div>
        </div>
      )}

      {/* Agent Response Panel (slide-in from right) */}
      {agentPanelOpen && (
        <div className="fixed inset-0 z-40 flex justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setAgentPanelOpen(false)}
          />
          {/* Panel */}
          <div className="relative w-full max-w-lg bg-background border-l border-border shadow-xl flex flex-col animate-in slide-in-from-right duration-200">
            {/* Panel header */}
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <div className="flex items-center gap-2">
                <Bot className="h-5 w-5 text-emerald-600" />
                <h2 className="text-lg font-semibold">Agent Fix Proposals</h2>
              </div>
              <button
                onClick={() => setAgentPanelOpen(false)}
                className="rounded-md p-1 hover:bg-muted transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Panel content - scrollable */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <pre className="whitespace-pre-wrap text-sm text-foreground font-mono bg-muted/50 rounded-lg p-4 border border-border">
                {agentResponse}
              </pre>
            </div>

            {/* Panel footer */}
            <div className="border-t border-border px-6 py-4 flex items-center gap-3">
              <button
                onClick={handleApplyAndRetry}
                disabled={retryLoading}
                className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {retryLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Apply & Retry
              </button>
              <button
                onClick={() => setAgentPanelOpen(false)}
                className="inline-flex items-center rounded-md px-4 py-2 text-sm font-medium border border-border hover:bg-muted transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Dialog */}
      {confirmDialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setConfirmDialog((prev) => ({ ...prev, open: false }))}
          />
          <div className="relative bg-background rounded-lg border border-border shadow-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">{confirmDialog.title}</h3>
            <p className="text-sm text-muted-foreground mb-6">{confirmDialog.message}</p>
            <div className="flex items-center gap-3 justify-end">
              <button
                onClick={() => setConfirmDialog((prev) => ({ ...prev, open: false }))}
                className="rounded-md px-4 py-2 text-sm font-medium border border-border hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDialog.onConfirm}
                className="rounded-md px-4 py-2 text-sm font-medium bg-orange-600 text-white hover:bg-orange-700 transition-colors"
              >
                Confirm Retry
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RecordRow({
  record,
  isExpanded,
  isSelected,
  showCheckboxColumn,
  isSelectable,
  onToggle,
  onSelect,
}: {
  record: SyncRecord;
  isExpanded: boolean;
  isSelected: boolean;
  showCheckboxColumn: boolean;
  isSelectable: boolean;
  onToggle: () => void;
  onSelect: () => void;
}) {
  const colSpan = showCheckboxColumn ? 9 : 8;
  return (
    <>
      <tr
        className={clsx(
          'border-b border-border/50 hover:bg-muted/30 cursor-pointer transition-colors',
          isSelected && 'bg-blue-50/50 dark:bg-blue-950/20'
        )}
      >
        {showCheckboxColumn && (
          <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
            {isSelectable ? (
              <input
                type="checkbox"
                checked={isSelected}
                onChange={onSelect}
                className="h-4 w-4 rounded border-border text-blue-600 focus:ring-blue-500"
              />
            ) : null}
          </td>
        )}
        <td className="px-4 py-3" onClick={onToggle}>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </td>
        <td className="px-4 py-3 font-mono text-xs" onClick={onToggle}>{record.pernr}</td>
        <td className="px-4 py-3" onClick={onToggle}>{record.name || '—'}</td>
        <td className="px-4 py-3" onClick={onToggle}>
          <span
            className={clsx(
              'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
              STATUS_BADGE_CLASSES[record.status] || ''
            )}
          >
            {record.status}
          </span>
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground" onClick={onToggle}>
          {record.error_type || '—'}
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground max-w-[200px] truncate" onClick={onToggle}>
          {record.error_message || '—'}
        </td>
        <td className="px-4 py-3 font-mono text-xs" onClick={onToggle}>{record.bp_id || '—'}</td>
        <td className="px-4 py-3 text-xs" onClick={onToggle}>{record.org_unit || '—'}</td>
      </tr>
      {isExpanded && (
        <tr className="border-b border-border/50 bg-muted/20">
          <td colSpan={colSpan} className="px-8 py-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-medium text-muted-foreground">PERNR:</span>{' '}
                <span className="font-mono">{record.pernr}</span>
              </div>
              <div>
                <span className="font-medium text-muted-foreground">Name:</span>{' '}
                {record.name || 'N/A'}
              </div>
              <div>
                <span className="font-medium text-muted-foreground">Status:</span>{' '}
                <span
                  className={clsx(
                    'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                    STATUS_BADGE_CLASSES[record.status] || ''
                  )}
                >
                  {record.status}
                </span>
              </div>
              <div>
                <span className="font-medium text-muted-foreground">Org Unit:</span>{' '}
                {record.org_unit || 'N/A'}
              </div>
              <div>
                <span className="font-medium text-muted-foreground">BP ID:</span>{' '}
                <span className="font-mono">{record.bp_id || 'N/A'}</span>
              </div>
              <div>
                <span className="font-medium text-muted-foreground">Error Type:</span>{' '}
                {record.error_type || 'N/A'}
              </div>
              <div className="col-span-2">
                <span className="font-medium text-muted-foreground">Error Message:</span>{' '}
                <span className="text-red-600 dark:text-red-400">
                  {record.error_message || 'No error'}
                </span>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
