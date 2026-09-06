import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Sparkles, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  Mail, 
  ArrowRight,
  Send
} from 'lucide-react';
import { authApi } from '../api/authApi';
import { useAuthStore } from '../stores/useAuthStore';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuthStore();

  const [status, setStatus] = useState('verifying'); // 'verifying' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState('');
  
  // Resend state
  const [resendEmail, setResendEmail] = useState(user?.email || '');
  const [resendLoading, setResendLoading] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [resendError, setResendError] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setErrorMessage('No verification token found in URL.');
      return;
    }

    let isMounted = true;
    const verify = async () => {
      try {
        await authApi.verifyEmail(token);
        if (isMounted) {
          setStatus('success');
        }
      } catch (err) {
        if (isMounted) {
          setStatus('error');
          setErrorMessage(
            err.message?.replace(/^API Error \(\d+\):\s*/, '') ||
            'The verification link is invalid, expired, or has already been used.'
          );
        }
      }
    };

    verify();
    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleResend = async (e) => {
    e.preventDefault();
    if (!resendEmail.trim()) {
      setResendError('Please enter your email address.');
      return;
    }

    setResendLoading(true);
    setResendError('');
    try {
      await authApi.resendVerification(resendEmail.trim());
      setResendSuccess(true);
    } catch (err) {
      setResendError(
        err.message?.replace(/^API Error \(\d+\):\s*/, '') ||
        'Failed to resend verification email.'
      );
    } finally {
      setResendLoading(false);
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
          {status === 'verifying' && (
            <div className="rounded-2xl border border-white/[0.08] bg-[#0E0F12] p-8 text-center space-y-4">
              <div className="h-12 w-12 mx-auto rounded-full bg-[#C9A86A]/10 flex items-center justify-center text-[#C9A86A]">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
              <div>
                <h2 className="text-xl font-medium text-[#F2F0EB]">Verifying your email</h2>
                <p className="text-xs text-[#A3A09A] mt-1.5 leading-relaxed">
                  Communicating with security servers to activate your account...
                </p>
              </div>
            </div>
          )}

          {status === 'success' && (
            <div className="rounded-2xl border border-[#C9A86A]/30 bg-[#C9A86A]/10 p-8 text-center space-y-6">
              <div className="h-12 w-12 mx-auto rounded-full bg-[#C9A86A]/20 flex items-center justify-center text-[#C9A86A]">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div className="space-y-1.5">
                <h2 className="text-2xl font-medium text-[#F2F0EB]">Email Verified</h2>
                <p className="text-xs text-[#A3A09A] leading-relaxed">
                  Your email has been successfully confirmed and your account is now fully active.
                </p>
              </div>
              <button
                type="button"
                onClick={() => navigate(isAuthenticated ? '/' : '/login')}
                className="w-full py-3.5 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs tracking-wider uppercase transition-all shadow-[0_4px_25px_rgba(201,168,106,0.18)]"
              >
                {isAuthenticated ? 'CONTINUE TO WORKSPACE' : 'SIGN IN TO TARK AI'}
              </button>
            </div>
          )}

          {status === 'error' && (
            <div className="space-y-6">
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 space-y-3">
                <div className="flex items-center gap-2.5 text-sm font-medium text-rose-300">
                  <AlertCircle className="h-5 w-5 text-rose-400 shrink-0" />
                  Verification Failed
                </div>
                <p className="text-xs text-rose-300/80 leading-relaxed">
                  {errorMessage}
                </p>
              </div>

              {/* Resend Option */}
              <div className="rounded-2xl border border-white/[0.08] bg-[#0E0F12] p-6 space-y-4">
                <div className="flex items-center gap-2 text-xs font-medium text-[#F2F0EB]">
                  <Mail className="h-4 w-4 text-[#C9A86A]" />
                  Request a new verification link
                </div>

                {resendSuccess ? (
                  <div className="rounded-xl border border-[#C9A86A]/30 bg-[#C9A86A]/10 p-4 text-xs text-[#C9A86A]">
                    If an account exists, a new verification email has been dispatched.
                  </div>
                ) : (
                  <form onSubmit={handleResend} className="space-y-3">
                    <input
                      type="email"
                      value={resendEmail}
                      onChange={(e) => setResendEmail(e.target.value)}
                      placeholder="name@example.com"
                      className="w-full px-4 py-2.5 rounded-xl bg-[#141518] border border-white/[0.08] text-xs text-[#F2F0EB] placeholder:text-[#74716C]/60 focus:outline-none focus:border-[#C9A86A]/60"
                    />
                    {resendError && (
                      <div className="text-xs text-rose-400">{resendError}</div>
                    )}
                    <button
                      type="submit"
                      disabled={resendLoading}
                      className="w-full py-2.5 rounded-xl bg-[#1E2024] hover:bg-[#282A30] text-[#F2F0EB] font-medium text-xs tracking-wide transition-all border border-white/[0.08] flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      {resendLoading ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#C9A86A]" />
                          <span>Sending...</span>
                        </>
                      ) : (
                        <>
                          <Send className="h-3.5 w-3.5 text-[#C9A86A]" />
                          <span>Resend verification email</span>
                        </>
                      )}
                    </button>
                  </form>
                )}
              </div>

              <div className="text-center">
                <Link
                  to="/login"
                  className="text-xs text-[#A3A09A] hover:text-[#C9A86A] transition-colors"
                >
                  Back to sign in
                </Link>
              </div>
            </div>
          )}
        </motion.div>
      </main>

      {/* Footer */}
      <footer className="w-full px-6 sm:px-12 lg:px-16 pb-8 text-center text-xs text-[#74716C]/50 z-20">
        TARK AI &middot; End-to-End Encrypted Session
      </footer>
    </div>
  );
}
