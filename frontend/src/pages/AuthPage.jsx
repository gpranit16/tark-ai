import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  Eye, 
  EyeOff, 
  Sparkles, 
  ChevronLeft, 
  AlertCircle, 
  Loader2,
  Check
} from 'lucide-react';
import { useAuthStore } from '../stores/useAuthStore';
import { authApi } from '../api/authApi';
import InteractiveAuthCharacter from '../components/auth/InteractiveAuthCharacter';

export default function AuthPage({ initialMode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || location.state?.from || '/';

  // Auth Mode: 'login' | 'signup' | 'forgot'
  const determineInitialMode = () => {
    if (initialMode) return initialMode;
    if (location.pathname === '/signup' || location.state?.mode === 'signup') return 'signup';
    return 'login';
  };

  const [authMode, setAuthMode] = useState(determineInitialMode);

  // Sync mode whenever URL or location state changes
  useEffect(() => {
    if (location.pathname === '/signup' || location.state?.mode === 'signup') {
      setAuthMode('signup');
    } else if (location.pathname === '/login' && !location.state?.mode) {
      setAuthMode('login');
    }
  }, [location.pathname, location.state]);

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // Form Input States
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [resetEmailSent, setResetEmailSent] = useState(false);
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotError, setForgotError] = useState(null);
  const [formErrors, setFormErrors] = useState({});

  // Character UI State
  const [focusedField, setFocusedField] = useState('none'); // 'none' | 'name' | 'email' | 'password' | 'confirmPassword'
  const [authStatus, setAuthStatus] = useState('idle'); // 'idle' | 'loading' | 'success' | 'error'

  const { login, signup, isLoading, error, clearError } = useAuthStore();

  // Active input length for pupil tracking
  const currentInputLength = 
    focusedField === 'name' ? name.length :
    focusedField === 'email' ? email.length :
    focusedField === 'password' ? password.length :
    focusedField === 'confirmPassword' ? confirmPassword.length : 0;

  const validateForm = () => {
    const errors = {};
    if (authMode === 'signup' && !name.trim()) {
      errors.name = 'Display name is required';
    }
    if (!email.trim()) {
      errors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Enter a valid email address';
    }
    if (authMode !== 'forgot') {
      if (!password) {
        errors.password = 'Password is required';
      } else if (password.length < 8) {
        errors.password = 'Password must be at least 8 characters';
      }
    }
    if (authMode === 'signup') {
      if (!confirmPassword) {
        errors.confirmPassword = 'Confirm your password';
      } else if (confirmPassword !== password) {
        errors.confirmPassword = 'Passwords do not match';
      }
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    clearError();
    setForgotError(null);
    if (!validateForm()) {
      setAuthStatus('error');
      return;
    }

    if (authMode === 'forgot') {
      setForgotLoading(true);
      setAuthStatus('loading');
      try {
        await authApi.forgotPassword(email.trim());
        setResetEmailSent(true);
        setAuthStatus('success');
      } catch (err) {
        const msg = err.message?.replace(/^API Error \(\d+\):\s*/, '') || 'Failed to send recovery link';
        setForgotError(msg);
        setAuthStatus('error');
      } finally {
        setForgotLoading(false);
      }
      return;
    }

    setAuthStatus('loading');
    try {
      if (authMode === 'login') {
        await login(email.trim(), password);
        setAuthStatus('success');
        setTimeout(() => {
          navigate(from, { replace: true });
        }, 450);
      } else if (authMode === 'signup') {
        await signup(email.trim(), password, name.trim());
        setAuthStatus('success');
        setTimeout(() => {
          navigate(from, { replace: true });
        }, 450);
      }
    } catch (err) {
      setAuthStatus('error');
    }
  };

  const switchMode = (newMode) => {
    setAuthMode(newMode);
    clearError();
    setForgotError(null);
    setFormErrors({});
    setAuthStatus('idle');
    setFocusedField('none');
    setShowPassword(false);
    setShowConfirmPassword(false);
    setResetEmailSent(false);
  };

  return (
    <div className="relative min-h-screen w-full bg-[#050505] text-[#F2F0EB] flex flex-col justify-between font-sans select-none overflow-x-hidden">
      {/* Top Header / Branding */}
      <header className="w-full px-6 sm:px-12 lg:px-16 pt-8 sm:pt-10 flex items-center justify-between z-20">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-[#C9A86A] to-[#8C6D37] p-[1px] shadow-[0_0_15px_rgba(201,168,106,0.2)]">
            <div className="h-full w-full bg-[#050505] rounded-[6px] flex items-center justify-center">
              <Sparkles className="h-3.5 w-3.5 text-[#C9A86A]" />
            </div>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="font-sans text-base font-semibold tracking-wider text-[#F2F0EB]">TARK</span>
            <span className="font-serif italic text-base text-[#C9A86A]">AI</span>
          </div>
        </div>
      </header>

      {/* Main Split Layout: Viewport Composition without Giant Card */}
      <main className="w-full flex-1 max-w-7xl mx-auto px-6 sm:px-12 lg:px-16 py-6 sm:py-10 flex flex-col lg:flex-row items-center justify-center gap-10 lg:gap-16 z-10">
        {/* ── LEFT ~42%: INTERACTIVE HUMAN CHARACTER ─────────────────── */}
        <div className="w-full lg:w-[42%] flex flex-col items-center justify-center relative">
          <InteractiveAuthCharacter
            focusedField={focusedField}
            isPasswordVisible={focusedField === 'confirmPassword' ? showConfirmPassword : showPassword}
            authStatus={authStatus}
            formMode={authMode}
            inputLength={currentInputLength}
          />
        </div>

        {/* ── RIGHT ~58%: AUTHENTICATION FORM AREA ──────────────────── */}
        <div className="w-full lg:w-[58%] max-w-md flex flex-col justify-center">
          {/* Top Switcher Tabs (Only for login / signup) */}
          {authMode !== 'forgot' && (
            <div className="inline-flex p-1 rounded-xl bg-[#0B0B0B] border border-white/[0.06] mb-8 self-start">
              <button
                type="button"
                onClick={() => switchMode('login')}
                className={`relative px-4 py-1.5 text-xs font-medium tracking-wide transition-colors duration-200 rounded-lg ${
                  authMode === 'login' ? 'text-[#F2F0EB]' : 'text-[#74716C] hover:text-[#A3A09A]'
                }`}
              >
                {authMode === 'login' && (
                  <motion.div
                    layoutId="auth-tab-pill"
                    className="absolute inset-0 rounded-lg bg-[#141416] border border-white/[0.08]"
                    transition={{ type: 'spring', bounce: 0.15, duration: 0.4 }}
                  />
                )}
                <span className="relative z-10">SIGN IN</span>
              </button>

              <button
                type="button"
                onClick={() => switchMode('signup')}
                className={`relative px-4 py-1.5 text-xs font-medium tracking-wide transition-colors duration-200 rounded-lg ${
                  authMode === 'signup' ? 'text-[#F2F0EB]' : 'text-[#74716C] hover:text-[#A3A09A]'
                }`}
              >
                {authMode === 'signup' && (
                  <motion.div
                    layoutId="auth-tab-pill"
                    className="absolute inset-0 rounded-lg bg-[#141416] border border-white/[0.08]"
                    transition={{ type: 'spring', bounce: 0.15, duration: 0.4 }}
                  />
                )}
                <span className="relative z-10">CREATE ACCOUNT</span>
              </button>
            </div>
          )}

          <AnimatePresence mode="wait">
            {/* ── FORGOT PASSWORD VIEW ─────────────────────────────── */}
            {authMode === 'forgot' ? (
              <motion.div
                key="forgot"
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                className="space-y-6"
              >
                <button
                  type="button"
                  onClick={() => switchMode('login')}
                  className="inline-flex items-center gap-1.5 text-xs text-[#A3A09A] hover:text-[#C9A86A] transition-colors"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                  Back to sign in
                </button>

                <div>
                  <h1 className="text-3xl sm:text-4xl font-medium tracking-tight text-[#F2F0EB]">
                    Reset password.
                  </h1>
                  <p className="text-sm text-[#A3A09A] mt-2 leading-relaxed">
                    Enter your email to receive a recovery link.
                  </p>
                </div>

                {forgotError && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.97 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 flex items-center gap-2.5 text-xs text-rose-300"
                  >
                    <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                    <span>{forgotError}</span>
                  </motion.div>
                )}

                {resetEmailSent ? (
                  <div className="rounded-2xl border border-[#C9A86A]/30 bg-[#C9A86A]/10 p-6 text-center space-y-2">
                    <div className="h-10 w-10 mx-auto rounded-full bg-[#C9A86A]/20 flex items-center justify-center text-[#C9A86A]">
                      <Check className="h-5 w-5" />
                    </div>
                    <div className="text-sm font-medium text-[#F2F0EB]">Check your email for a password reset link.</div>
                    <div className="text-xs text-[#A3A09A] leading-relaxed">
                      If an account exists for <span className="text-[#C9A86A]">{email}</span>, recovery instructions have been sent.
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-5">
                    <div>
                      <label className="block text-xs font-medium text-[#A3A09A] mb-2">
                        Email
                      </label>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        onFocus={() => setFocusedField('email')}
                        onBlur={() => setFocusedField('none')}
                        placeholder="name@example.com"
                        className="w-full px-4 py-3 rounded-xl bg-[#111214] border border-white/[0.08] text-sm text-[#F2F0EB] placeholder:text-[#74716C]/60 focus:outline-none focus:border-[#C9A86A]/60 focus:bg-[#141518] transition-all font-normal"
                      />
                      {formErrors.email && (
                        <div className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                          <AlertCircle className="h-3 w-3" /> {formErrors.email}
                        </div>
                      )}
                    </div>

                    <button
                      type="submit"
                      disabled={forgotLoading}
                      className="w-full py-3.5 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs tracking-wider uppercase transition-all shadow-[0_4px_20px_rgba(201,168,106,0.15)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {forgotLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin text-black" />
                          <span>SENDING INSTRUCTIONS...</span>
                        </>
                      ) : (
                        <span>SEND INSTRUCTIONS</span>
                      )}
                    </button>
                  </form>
                )}
              </motion.div>
            ) : (
              /* ── LOGIN / SIGNUP VIEW ────────────────────────────── */
              <motion.div
                key={authMode}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                className="space-y-6"
              >
                {/* Heading & Subtitle */}
                <div>
                  <h1 className="text-3xl sm:text-4xl font-medium tracking-tight text-[#F2F0EB]">
                    {authMode === 'login' ? 'Welcome back.' : 'Get started with TARK AI.'}
                  </h1>
                  <p className="text-sm text-[#A3A09A] mt-2">
                    {authMode === 'login' ? 'Sign in to continue to TARK AI.' : 'Create your account and make TARK AI yours.'}
                  </p>
                </div>

                {/* Error Banner */}
                {error && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.97 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 flex items-center gap-2.5 text-xs text-rose-300"
                  >
                    <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                    <span>{error}</span>
                  </motion.div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                  {/* Display Name (Signup Only) */}
                  {authMode === 'signup' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <label className="block text-xs font-medium text-[#A3A09A] mb-1.5">
                        Display name
                      </label>
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onFocus={() => setFocusedField('name')}
                        onBlur={() => setFocusedField('none')}
                        placeholder="Alex Mercer"
                        className="w-full px-4 py-3 rounded-xl bg-[#111214] border border-white/[0.08] text-sm text-[#F2F0EB] placeholder:text-[#74716C]/60 focus:outline-none focus:border-[#C9A86A]/60 focus:bg-[#141518] transition-all font-normal"
                      />
                      {formErrors.name && (
                        <div className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                          <AlertCircle className="h-3 w-3" /> {formErrors.name}
                        </div>
                      )}
                    </motion.div>
                  )}

                  {/* Email Input */}
                  <div>
                    <label className="block text-xs font-medium text-[#A3A09A] mb-1.5">
                      Email
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      onFocus={() => setFocusedField('email')}
                      onBlur={() => setFocusedField('none')}
                      placeholder="name@example.com"
                      className="w-full px-4 py-3 rounded-xl bg-[#111214] border border-white/[0.08] text-sm text-[#F2F0EB] placeholder:text-[#74716C]/60 focus:outline-none focus:border-[#C9A86A]/60 focus:bg-[#141518] transition-all font-normal"
                    />
                    {formErrors.email && (
                      <div className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" /> {formErrors.email}
                      </div>
                    )}
                  </div>

                  {/* Password Input */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-medium text-[#A3A09A]">
                        Password
                      </label>
                      {authMode === 'login' && (
                        <button
                          type="button"
                          onClick={() => switchMode('forgot')}
                          className="text-xs text-[#A3A09A] hover:text-[#C9A86A] transition-colors"
                        >
                          Forgot password?
                        </button>
                      )}
                    </div>
                    <div className="relative">
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onFocus={() => setFocusedField('password')}
                        onBlur={() => setFocusedField('none')}
                        placeholder="••••••••••••"
                        className="w-full pl-4 pr-11 py-3 rounded-xl bg-[#111214] border border-white/[0.08] text-sm text-[#F2F0EB] placeholder:text-[#74716C]/60 focus:outline-none focus:border-[#C9A86A]/60 focus:bg-[#141518] transition-all font-mono"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#74716C] hover:text-[#F2F0EB] transition-colors"
                        title={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    {formErrors.password && (
                      <div className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" /> {formErrors.password}
                      </div>
                    )}
                  </div>

                  {/* Confirm Password (Signup Only) */}
                  {authMode === 'signup' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <label className="block text-xs font-medium text-[#A3A09A] mb-1.5">
                        Confirm password
                      </label>
                      <div className="relative">
                        <input
                          type={showConfirmPassword ? 'text' : 'password'}
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          onFocus={() => setFocusedField('confirmPassword')}
                          onBlur={() => setFocusedField('none')}
                          placeholder="••••••••••••"
                          className="w-full pl-4 pr-11 py-3 rounded-xl bg-[#111214] border border-white/[0.08] text-sm text-[#F2F0EB] placeholder:text-[#74716C]/60 focus:outline-none focus:border-[#C9A86A]/60 focus:bg-[#141518] transition-all font-mono"
                        />
                        <button
                          type="button"
                          onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                          className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#74716C] hover:text-[#F2F0EB] transition-colors"
                          title={showConfirmPassword ? "Hide password" : "Show password"}
                        >
                          {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                      {formErrors.confirmPassword && (
                        <div className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                          <AlertCircle className="h-3 w-3" /> {formErrors.confirmPassword}
                        </div>
                      )}
                    </motion.div>
                  )}

                  {/* Primary Submit Button */}
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full mt-2 py-3.5 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs tracking-wider uppercase transition-all shadow-[0_4px_25px_rgba(201,168,106,0.18)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin text-black" />
                        <span>{authMode === 'login' ? 'Signing in...' : 'Creating account...'}</span>
                      </>
                    ) : (
                      <span>{authMode === 'login' ? 'SIGN IN' : 'CREATE ACCOUNT'}</span>
                    )}
                  </button>
                </form>

                {/* Bottom Switcher */}
                <div className="pt-2 text-xs text-[#A3A09A]">
                  {authMode === 'login' ? (
                    <>
                      Don't have an account?{' '}
                      <button
                        type="button"
                        onClick={() => switchMode('signup')}
                        className="text-[#C9A86A] hover:underline font-medium ml-0.5"
                      >
                        Create account
                      </button>
                    </>
                  ) : (
                    <>
                      Already have an account?{' '}
                      <button
                        type="button"
                        onClick={() => switchMode('login')}
                        className="text-[#C9A86A] hover:underline font-medium ml-0.5"
                      >
                        Sign in
                      </button>
                    </>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Subtle Footer */}
      <footer className="w-full px-6 sm:px-12 lg:px-16 pb-8 text-center text-xs text-[#74716C]/50 z-20">
        TARK AI &middot; End-to-End Encrypted Session
      </footer>
    </div>
  );
}
