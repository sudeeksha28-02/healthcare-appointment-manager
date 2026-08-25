import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { loginUser } from '../services/api';
import { Activity, Lock, Mail, ArrowRight, ShieldCheck, Stethoscope, UserCheck } from 'lucide-react';

export const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const res = await loginUser({ email, password });
      login(res.data.access_token, res.data.role);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid email or password');
    } finally {
      setSubmitting(false);
    }
  };

  const fillQuickLogin = (demoEmail, demoPassword) => {
    setEmail(demoEmail);
    setPassword(demoPassword);
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-4">
      <div className="max-w-md w-full glass-panel rounded-2xl p-8 shadow-2xl relative overflow-hidden">
        
        {/* Top glow decoration */}
        <div className="absolute -top-24 -left-24 w-48 h-48 bg-sky-500/20 rounded-full blur-3xl pointer-events-none"></div>
        <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-emerald-500/20 rounded-full blur-3xl pointer-events-none"></div>

        <div className="text-center mb-8">
          <div className="inline-flex w-14 h-14 rounded-2xl bg-gradient-to-tr from-sky-500 to-emerald-400 items-center justify-center mb-4 shadow-lg glow-cyan">
            <Activity className="w-8 h-8 text-slate-950 stroke-[2.5]" />
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Welcome back</h1>
          <p className="text-sm text-slate-400 mt-1">Sign in to manage your appointments & medical care</p>
        </div>

        {error && (
          <div className="mb-6 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                className="w-full bg-slate-950/60 border border-slate-800 rounded-xl pl-11 pr-4 py-3 text-slate-200 text-sm focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              Password
            </label>
            <div className="relative">
              <Lock className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-slate-950/60 border border-slate-800 rounded-xl pl-11 pr-4 py-3 text-slate-200 text-sm focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition-all"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-sky-500 to-emerald-500 hover:from-sky-400 hover:to-emerald-400 text-slate-950 font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-sky-500/20 transition-all disabled:opacity-50"
          >
            {submitting ? 'Authenticating...' : (
              <>
                <span>Sign In</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Quick Demo Logins */}
        <div className="mt-8 pt-6 border-t border-slate-800">
          <span className="block text-xs text-center text-slate-400 mb-3">Quick Demo Logins</span>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => fillQuickLogin('admin@healthcare.com', 'adminpassword123')}
              className="px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-300 text-xs font-medium flex items-center justify-center gap-1.5 transition-all"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              <span>System Admin</span>
            </button>
            <button
              onClick={() => fillQuickLogin('patient@test.com', 'patientpw')}
              className="px-2.5 py-1.5 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/20 text-sky-300 text-xs font-medium flex items-center justify-center gap-1.5 transition-all"
            >
              <UserCheck className="w-3.5 h-3.5 text-sky-400" />
              <span>Demo Patient</span>
            </button>
          </div>
        </div>

        <div className="mt-6 text-center text-xs text-slate-400">
          Don't have a patient account?{' '}
          <Link to="/register" className="text-sky-400 font-semibold hover:underline">
            Register here
          </Link>
        </div>

      </div>
    </div>
  );
};
