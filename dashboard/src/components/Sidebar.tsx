import { NavLink } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  LayoutDashboard,
  Settings,
  Workflow,
  Bot,
  ClipboardList,
  List,
  LogOut,
  User,
  Users,
  ChevronUp,
  BookOpen,
  GitBranch,
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, alwaysVisible: true },
  { to: '/records', label: 'Records', icon: List, alwaysVisible: true },
  { to: '/workflows', label: 'Workflows', icon: Workflow, alwaysVisible: true },
  { to: '/agent', label: 'Agent', icon: Bot, alwaysVisible: true },
  { to: '/users', label: 'Users', icon: Users, alwaysVisible: true },
  { to: '/audit', label: 'Audit Log', icon: ClipboardList, alwaysVisible: true },
  { to: '/methodology', label: 'Methodology', icon: BookOpen, alwaysVisible: true },
  { to: '/process', label: 'Process Flow', icon: GitBranch, alwaysVisible: true },
  { to: '/settings', label: 'Settings', icon: Settings, alwaysVisible: false },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm font-bold">
          BP
        </div>
        <span className="text-sm font-semibold">BPSYNC Dashboard</span>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {navItems.filter(item => item.alwaysVisible).map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User avatar with dropdown */}
      <div className="border-t border-border p-3 relative" ref={menuRef}>
        {user && (
          <>
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs hover:bg-accent/50 transition-colors"
            >
              <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                <User className="h-3.5 w-3.5 text-primary" />
              </div>
              <div className="truncate text-left flex-1">
                <span className="font-medium block truncate text-foreground">{user.name}</span>
                {user.email && <span className="text-muted-foreground block truncate text-[10px]">{user.email}</span>}
              </div>
              <ChevronUp className={clsx("h-3 w-3 text-muted-foreground transition-transform", showUserMenu ? "" : "rotate-180")} />
            </button>

            {/* Dropdown menu */}
            {showUserMenu && (
              <div className="absolute bottom-full left-3 right-3 mb-1 rounded-md border border-border bg-card shadow-lg py-1 z-50">
                <NavLink
                  to="/profile"
                  onClick={() => setShowUserMenu(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-accent/50 transition-colors"
                >
                  <User className="h-3 w-3" />
                  Profile
                </NavLink>
                <NavLink
                  to="/settings"
                  onClick={() => setShowUserMenu(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-accent/50 transition-colors"
                >
                  <Settings className="h-3 w-3" />
                  Settings
                </NavLink>
                <div className="border-t border-border my-1" />
                <button
                  onClick={() => { setShowUserMenu(false); logout(); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-xs text-red-500 hover:bg-red-500/10 transition-colors"
                >
                  <LogOut className="h-3 w-3" />
                  Logout
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
