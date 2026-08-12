import { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { Store, MessageSquare, Database, Settings, Bot, MessagesSquare } from 'lucide-react';

interface Props {
  children: ReactNode;
}

const navItems = [
  { to: '/', label: 'Store', icon: Store, end: true },
  { to: '/assistant', label: 'Assistant', icon: MessageSquare, end: false },
  { to: '/explorer', label: 'Explorer', icon: Database, end: false },
  { to: '/conversations', label: 'Conversations', icon: MessagesSquare, end: false },
  { to: '/admin', label: 'Admin', icon: Settings, end: false },
];

export default function Layout({ children }: Props) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-sm">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div className="leading-tight">
              <p className="font-semibold text-slate-900">ProductChat</p>
              <p className="text-[11px] text-slate-400 -mt-0.5">AI shopping assistant</p>
            </div>
          </div>

          <nav className="flex items-center gap-1">
            {navItems.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main>{children}</main>
    </div>
  );
}
