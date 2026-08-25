import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Activity, LogOut, Calendar, ShieldCheck, UserCheck, Stethoscope } from 'lucide-react';
import { getGoogleStatus, getGoogleLoginUrl, disconnectGoogle } from '../services/api';

export const Navbar = () => {
  const { user, logout } = useAuth();
  const [googleConnected, setGoogleConnected] = useState(false);
  const [loadingGoogle, setLoadingGoogle] = useState(false);

  useEffect(() => {
    if (user) {
      checkGoogleStatus();
    }
  }, [user]);

  const checkGoogleStatus = async () => {
    try {
      const res = await getGoogleStatus();
      setGoogleConnected(res.data.connected);
    } catch (err) {
      setGoogleConnected(false);
    }
  };

  const handleConnectGoogle = async () => {
    setLoadingGoogle(true);
    try {
      const res = await getGoogleLoginUrl();
      if (res.data.url) {
        window.location.href = res.data.url;
      }
    } catch (err) {
      alert("Google Calendar integration is not configured on the backend server.");
    } finally {
      setLoadingGoogle(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    if (window.confirm("Are you sure you want to disconnect Google Calendar?")) {
      try {
        await disconnectGoogle();
        setGoogleConnected(false);
      } catch (err) {
        alert("Failed to disconnect Google Calendar.");
      }
    }
  };

  const getRoleBadge = (role) => {
    switch (role) {
      case 'admin':
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20"><ShieldCheck className="w-3.5 h-3.5" /> Admin</span>;
      case 'doctor':
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><Stethoscope className="w-3.5 h-3.5" /> Doctor</span>;
      default:
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20"><UserCheck className="w-3.5 h-3.5" /> Patient</span>;
    }
  };

  return (
    <header className="sticky top-0 z-40 glass-panel border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-500 to-emerald-400 flex items-center justify-center shadow-lg glow-cyan">
            <Activity className="w-6 h-6 text-slate-950 stroke-[2.5]" />
          </div>
          <div>
            <span className="text-xl font-bold bg-gradient-to-r from-white via-slate-200 to-sky-400 bg-clip-text text-transparent">
              CareSync
            </span>
            <span className="hidden sm:inline-block ml-2 text-xs font-medium text-slate-400">
              Healthcare Manager
            </span>
          </div>
        </div>

        {/* User Info & OAuth Widget */}
        {user && (
          <div className="flex items-center gap-4">
            
            {/* Google Calendar Sync Widget */}
            {googleConnected ? (
              <button
                onClick={handleDisconnectGoogle}
                className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all"
                title="Google Calendar Synced. Click to disconnect."
              >
                <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                <span>Google Sync Active</span>
              </button>
            ) : (
              <button
                onClick={handleConnectGoogle}
                disabled={loadingGoogle}
                className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700/80 hover:text-white transition-all"
              >
                <Calendar className="w-3.5 h-3.5 text-sky-400" />
                <span>Link Google Calendar</span>
              </button>
            )}

            {/* Profile Info */}
            <div className="flex items-center gap-3 pl-3 border-l border-slate-800">
              <div className="text-right hidden md:block">
                <div className="text-sm font-semibold text-slate-200">
                  {user.first_name} {user.last_name}
                </div>
                <div className="text-xs text-slate-400">{user.email}</div>
              </div>
              
              {getRoleBadge(user.role)}

              <button
                onClick={logout}
                className="p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-all"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>

          </div>
        )}

      </div>
    </header>
  );
};
