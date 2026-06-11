import { useState, useEffect } from 'react';
import { useSettings } from '../hooks/useSettings';
import { Card } from '../components/Card';
import { Input } from '../components/Input';
import { Select } from '../components/Select';
import { Button } from '../components/Button';
import { showToast } from '../components/Toast';
import { api } from '../lib/api';
import { Shield, Users, ChevronDown, ChevronRight, Loader2, Check, Info } from 'lucide-react';

interface Role {
  id: string;
  name: string;
  description: string;
  permissions: string[];
}

interface IASGroup {
  id: string;
  displayName: string;
}

interface GroupMember {
  value: string;
  display: string;
  type: string;
}

interface AuthzConfig {
  enabled: boolean;
  scim_url: string;
  scim_user: string;
  scim_password: string;
  viewer_group: string;
  editor_group: string;
  admin_group: string;
  super_admin_group: string;
}

export function AuthorizationTab() {
  const { settings } = useSettings();
  const [roles, setRoles] = useState<Role[]>([]);
  const [groups, setGroups] = useState<IASGroup[]>([]);
  const [config, setConfig] = useState<AuthzConfig>({
    enabled: false,
    scim_url: '',
    scim_user: '',
    scim_password: '',
    viewer_group: '',
    editor_group: '',
    admin_group: '',
    super_admin_group: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [myRole, setMyRole] = useState<any>(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    const [rolesRes, configRes, myRoleRes] = await Promise.all([
      api.get<{ roles: Role[] }>('/api/authz/roles'),
      api.get<AuthzConfig>('/api/authz/config'),
      api.get<any>('/api/authz/my-role'),
    ]);
    if (rolesRes.ok && rolesRes.data) setRoles((rolesRes.data as any).roles || []);
    if (configRes.ok && configRes.data) setConfig(configRes.data as AuthzConfig);
    if (myRoleRes.ok && myRoleRes.data) setMyRole(myRoleRes.data);
    setLoading(false);
  };

  const fetchGroups = async () => {
    setLoadingGroups(true);
    const payload = {
      ...config,
      scim_url: settings.auth?.iasUrl ? `${settings.auth.iasUrl}/scim` : config.scim_url,
    };
    const res = await api.post<{ groups: IASGroup[] }>('/api/authz/groups', payload);
    if (res.ok && res.data && (res.data as any).groups) {
      setGroups((res.data as any).groups);
      setMessage('');
    } else {
      setMessage((res.data as any)?.error || 'Failed to fetch groups');
    }
    setLoadingGroups(false);
  };

  const fetchMembers = async (groupId: string) => {
    if (expandedGroup === groupId) {
      setExpandedGroup(null);
      return;
    }
    setExpandedGroup(groupId);
    setLoadingMembers(true);
    const res = await api.get<any>(`/api/authz/groups/${groupId}/members`);
    if (res.ok && res.data && res.data.members) {
      setMembers(res.data.members);
    } else {
      setMembers([]);
    }
    setLoadingMembers(false);
  };

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      ...config,
      scim_url: settings.auth?.iasUrl ? `${settings.auth.iasUrl}/scim` : config.scim_url,
    };
    const res = await api.put<any>('/api/authz/config', payload);
    if (res.ok) {
      showToast('success', 'Authorization configuration saved successfully');
    } else {
      showToast('error', res.data?.error || res.error || 'Save failed');
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const groupOptions = [
    { value: '', label: '-- Not mapped --' },
    ...groups.map((g) => ({ value: g.displayName, label: g.displayName })),
  ];

  return (
    <div className="space-y-6">
      {/* Current User Role */}
      {myRole && (
        <div className="rounded-md bg-muted/50 border border-border p-3 flex items-center gap-3">
          <Shield className="h-4 w-4 text-primary" />
          <div className="text-sm">
            <span className="text-muted-foreground">Your current role: </span>
            <span className="font-semibold">{myRole.role?.name || 'Unknown'}</span>
            {!config.enabled && (
              <span className="text-xs text-muted-foreground ml-2">(Authorization disabled — all users have full access)</span>
            )}
          </div>
        </div>
      )}

      {/* Enable/Disable */}
      <Card title="Authorization Control" description="Enable role-based access control using IAS user groups">
        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
              className="h-4 w-4"
            />
            <div>
              <span className="text-sm font-medium">Enable authorization</span>
              <p className="text-xs text-muted-foreground">
                When enabled, users must belong to a mapped IAS group to access the app. When disabled, all authenticated users have full access.
              </p>
            </div>
          </label>

          {config.enabled && (
            <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 p-3 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2">
              <Info className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <span>Make sure to assign yourself to the Super Admin group before saving, otherwise you may lose access to this page.</span>
            </div>
          )}
        </div>
      </Card>

      {/* SCIM Credentials */}
      <Card title="IAS SCIM API Credentials" description="API client credentials for reading IAS groups and members (read-only)">
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-foreground block mb-1.5">SCIM API URL</label>
            <div className="flex h-9 w-full items-center rounded-md border border-input bg-muted/50 px-3 py-1 text-sm text-muted-foreground">
              {settings.auth?.iasUrl ? `${settings.auth.iasUrl}/scim` : '— Configure IAS URL in Auth tab first —'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Derived from Auth tab IAS Tenant URL</p>
          </div>
          <Input
            label="Client ID"
            value={config.scim_user}
            onChange={(e) => setConfig({ ...config, scim_user: e.target.value })}
            placeholder="Client ID from IAS System Administrator"
          />
          <Input
            label="Client Secret"
            type="password"
            value={config.scim_password}
            onChange={(e) => setConfig({ ...config, scim_password: e.target.value })}
            placeholder="••••••••"
          />
          <Button variant="outline" size="sm" onClick={fetchGroups} loading={loadingGroups}>
            Fetch IAS Groups
          </Button>
          {message && <p className="text-xs text-muted-foreground">{message}</p>}
        </div>
      </Card>

      {/* Role-to-Group Mapping */}
      <Card title="Role Mapping" description="Map each application role to an IAS user group">
        <div className="space-y-4">
          {groups.length === 0 && (
            <p className="text-xs text-muted-foreground">Enter SCIM credentials and click "Fetch IAS Groups" to load groups for mapping.</p>
          )}
          {roles.map((role) => {
            const configKey = `${role.id}_group` as keyof AuthzConfig;
            return (
              <div key={role.id} className="border border-border rounded-md p-3">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-medium">{role.name}</span>
                    <p className="text-xs text-muted-foreground">{role.description}</p>
                  </div>
                </div>
                <Select
                  label=""
                  value={(config[configKey] as string) || ''}
                  onChange={(e) => setConfig({ ...config, [configKey]: e.target.value })}
                  options={groupOptions}
                />
                <div className="flex flex-wrap gap-1 mt-2">
                  {role.permissions.map((p) => (
                    <span key={p} className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Save */}
      <div className="flex justify-end">
        <Button onClick={handleSave} loading={saving}>
          <Check className="h-4 w-4" />
          Save Authorization Config
        </Button>
      </div>

      {/* Group Members Viewer */}
      {groups.length > 0 && (
        <Card title="Group Members" description="Click a group to view its members (read-only from IAS SCIM)">
          <div className="space-y-1 max-h-[400px] overflow-y-auto">
            {groups.map((group) => (
              <div key={group.id} className="border border-border rounded-md">
                <button
                  onClick={() => fetchMembers(group.id)}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-muted/50 transition-colors text-left"
                >
                  {expandedGroup === group.id ? (
                    <ChevronDown className="h-3 w-3" />
                  ) : (
                    <ChevronRight className="h-3 w-3" />
                  )}
                  <Users className="h-3 w-3 text-muted-foreground" />
                  <span className="font-medium">{group.displayName}</span>
                </button>
                {expandedGroup === group.id && (
                  <div className="px-3 pb-3 border-t border-border">
                    {loadingMembers ? (
                      <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Loading members...
                      </div>
                    ) : members.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">No members in this group</p>
                    ) : (
                      <table className="w-full text-xs mt-2">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left py-1 px-2 text-muted-foreground font-medium">#</th>
                            <th className="text-left py-1 px-2 text-muted-foreground font-medium">Name</th>
                            <th className="text-left py-1 px-2 text-muted-foreground font-medium">Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {members.map((m, idx) => (
                            <tr key={m.value} className="border-b border-border last:border-0">
                              <td className="py-1 px-2 text-muted-foreground">{idx + 1}</td>
                              <td className="py-1 px-2">{m.display || m.value}</td>
                              <td className="py-1 px-2 text-muted-foreground">{m.type || 'User'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
