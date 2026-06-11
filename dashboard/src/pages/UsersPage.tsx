import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { Card } from '../components/Card';
import { Input } from '../components/Input';
import { Users, Search, Clock, LogIn, Shield, Mail, User as UserIcon } from 'lucide-react';

interface AppUser {
  user_id: string;
  display_name: string;
  email: string;
  given_name: string;
  family_name: string;
  groups: string[];
  first_login: string;
  last_login: string;
  login_count: number;
  status: string;
}

export function UsersPage() {
  const [users, setUsers] = useState<AppUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    const res = await api.get<any>('/api/users');
    if (res.ok && res.data?.users) {
      setUsers(res.data.users);
    }
    setLoading(false);
  };

  const filteredUsers = users.filter(
    (u) =>
      u.display_name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.user_id.toLowerCase().includes(search.toLowerCase())
  );

  const formatDate = (iso: string) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const timeAgo = (iso: string) => {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Users</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Users auto-registered via SAP IAS login ({users.length} total)
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-md border border-border p-4 flex items-center gap-3">
          <Users className="h-5 w-5 text-primary" />
          <div>
            <p className="text-2xl font-bold">{users.length}</p>
            <p className="text-xs text-muted-foreground">Total Users</p>
          </div>
        </div>
        <div className="rounded-md border border-border p-4 flex items-center gap-3">
          <LogIn className="h-5 w-5 text-emerald-600" />
          <div>
            <p className="text-2xl font-bold">{users.filter((u) => {
              const diff = Date.now() - new Date(u.last_login).getTime();
              return diff < 86400000; // 24h
            }).length}</p>
            <p className="text-xs text-muted-foreground">Active Today</p>
          </div>
        </div>
        <div className="rounded-md border border-border p-4 flex items-center gap-3">
          <Clock className="h-5 w-5 text-blue-600" />
          <div>
            <p className="text-2xl font-bold">{users.reduce((sum, u) => sum + u.login_count, 0)}</p>
            <p className="text-xs text-muted-foreground">Total Logins</p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, email, or ID..."
          className="w-full pl-9 pr-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {/* Users Table */}
      <Card>
        {filteredUsers.length === 0 ? (
          <div className="text-center py-8 text-sm text-muted-foreground">
            {users.length === 0
              ? 'No users yet. Users are auto-registered on first IAS login.'
              : 'No users match your search.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">User</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Groups</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">First Login</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Last Login</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Logins</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => (
                  <tr key={user.user_id} className="border-b border-border last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                          <UserIcon className="h-4 w-4 text-primary" />
                        </div>
                        <div>
                          <p className="font-medium">{user.display_name}</p>
                          <p className="text-xs text-muted-foreground flex items-center gap-1">
                            <Mail className="h-3 w-3" />
                            {user.email || '—'}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {user.groups.length > 0 ? (
                          user.groups.map((g) => (
                            <span
                              key={g}
                              className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px]"
                            >
                              <Shield className="h-2.5 w-2.5" />
                              {g}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {formatDate(user.first_login)}
                    </td>
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-xs">{timeAgo(user.last_login)}</p>
                        <p className="text-[10px] text-muted-foreground">{formatDate(user.last_login)}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="inline-flex items-center justify-center h-6 min-w-[24px] rounded-full bg-muted px-2 text-xs font-medium">
                        {user.login_count}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
