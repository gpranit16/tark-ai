import React, { useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Sparkles, 
  Eye, 
  EyeOff, 
  AlertCircle, 
  CheckCircle2, 
  Loader2,
  Lock,
  ArrowRight
} from 'lucide-react';
import { authApi } from '../api/authApi';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  const [formError, setFormError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');

    if (!token) {
      setFormError('Invalid or missing password reset token. Please request a new link.');
      return;
    }

    if (!password) {
      setFormError('Please enter a new password.');
      return;
    }

    if (password.length < 8) {
      setFormError('Password must be at least 8 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setFormError('Passwords do not match.');
      return;
    }

    setIsLoading(true);
    try {
      await authApi.resetPassword({ token, newPassword: password });
      setIsSuccess(true);
    } catch (err) {
      const msg = err.message?.replace(/^API Error \(\d+\):\s*/, '') || 'Failed to reset password. The link may have expired.';
      setFormError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full bg-[#050505] text-[#F2F0EB] flex flex-col justify-between font-sans select-none overflow-x-hidden">
      {/* Top Header */}
      <header className="w-full px-6 sm:px-12 lg:px-16 pt-8 sm:pt-10 flex items-center justify-between z-20">
        <Link to="/login" className="flex items-center gap-2.5 hover:opacity-90 transition-opacity">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-[#C9A86A] to-[#8C6D37] p-[1px] shadow-[0_0_15px_rgba(201,168,106,0.2)]">
            <div className="h-full w-full bg-[#050505] rounded-[6px] flex items-center justify-center">
              <Sparkles className="h-3.5 w-3.5 text-[#C9A86A]" />
            </div>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="font-sans text-base font-semibold tracking-wider text-[#F2F0EB]">TARK</span>
            <span className="font-serif italic text-base text-[#C9A86A]">AI</span>
          </div>
        </Link>
      </header>

      {/* Main Container */}
      <main className="w-full flex-1 max-w-md mx-auto px-6 py-12 flex flex-col justify-center z-10">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-6"
        >
          <div>
            <h1 className="text-3xl font-medium tracking-tight text-[#F2F0EB]">
              Choose a new password
            </h1>
            <p className="text-sm text-[#A3A09A] mt-2 leading-relaxed">
              Your new password must be at least 8 characters long.
            </p>
          </div>

          {!token && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 space-y-3 text-xs text-rose-300">
              <div className="flex items-center gap-2 font-medium">
                <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
                Missing or invalid token
              </div>
              <p className="text-[#A3A09A]">
                No password reset token was detected in your link. Please request a new recovery link.
              </p>
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 text-xs text-[#C9A86A] hover:underline font-medium"
              >
                Back to Sign in <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          )}

          {formError && (
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 flex items-center gap-2.5 text-xs text-rose-300"
            >
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{formError}</span>
            </motion.div>
          )}

          {isSuccess ? (
            <div className="rounded-2xl border border-[#C9A86A]/30 bg-[#C9A86A]/10 p-6 text-center space-y-4">
              <div className="h-12 w-12 mx-auto rounded-full bg-[#C9A86A]/20 flex items-center justify-center text-[#C9A86A]">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div className="space-y-1">
                <div className="text-base font-medium text-[#F2F0EB]">Password Reset Complete</div>
                <div className="text-xs text-[#A3A09A] leading-relaxed">
                  Your password has been securely updated. You can now sign in with your new credentials.
                </div>
              </div>
              <button
                type="button"
                onClick={() => navigate('/login')}
                className="w-full py-3 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs tracking-wider uppercase transition-all shadow-[0_4px_20px_rgba(201,168,106,0.15)]"
              >
                SIGN IN NOW
              </button>
            </div>
          ) : (
            token && (
              <form onSubmit={handleSubmit} className="space-y-4">
                {/* New Password */}
                <div>
                  <label className="block text-xs font-medium text-[#A3A09A] mb-1.5">
                    New password
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
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
                </div>

                {/* Confirm Password */}
                <div>
                  <label className="block text-xs font-medium text-[#A3A09A] mb-1.5">
                    Confirm new password
                  </label>
                  <div className="relative">
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
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
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full mt-2 py-3.5 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs tracking-wider uppercase transition-all shadow-[0_4px_25px_rgba(201,168,106,0.18)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin text-black" />
                      <span>UPDATING PASSWORD...</span>
                    </>
                  ) : (
                    <span>UPDATE PASSWORD</span>
                  )}
                </button>
              </form>
            )
          )}

          <div className="pt-2 text-center">
            <Link
              to="/login"
              className="text-xs text-[#A3A09A] hover:text-[#C9A86A] transition-colors"
            >
              Back to sign in
            </Link>
          </div>
        </motion.div>
      </main>

      {/* Footer */}
      <footer className="w-full px-6 sm:px-12 lg:px-16 pb-8 text-center text-xs text-[#74716C]/50 z-20">
        TARK AI &middot; End-to-End Encrypted Session
      </footer>
    </div>
  );
}
