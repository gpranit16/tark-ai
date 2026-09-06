import React, { useState, useRef } from 'react';
import {
  X,
  User,
  Shield,
  UploadCloud,
  Check,
  AlertCircle,
  Copy,
  Sparkles,
  Lock,
  Eye,
  EyeOff,
  RefreshCw,
  Trash2,
  Mail,
  Calendar,
  CheckCircle2,
  Fingerprint,
} from 'lucide-react';
import clsx from 'clsx';
import { useAuthStore } from '../../stores/useAuthStore';
import { authApi } from '../../api/authApi';

// Curated Luxury Preset Avatars for TARK AI
const PRESET_AVATARS = [
  {
    id: 'gold_core',
    name: 'TARK Gold Core',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="g" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="%23FFE6A3"/><stop offset="50%" stop-color="%23C9A86A"/><stop offset="100%" stop-color="%2318140E"/></radialGradient></defs><rect width="100" height="100" rx="24" fill="%230E0E10"/><circle cx="50" cy="50" r="32" fill="url(%23g)" stroke="%23FFE6A3" stroke-width="2"/><path d="M50 26 L56 44 L74 50 L56 56 L50 74 L44 56 L26 50 L44 44 Z" fill="%23FFFFFF" opacity="0.9"/></svg>`,
  },
  {
    id: 'cyber_obsidian',
    name: 'Cyber Obsidian',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="o" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%232A2A30"/><stop offset="100%" stop-color="%2308080A"/></linearGradient></defs><rect width="100" height="100" rx="24" fill="url(%23o)" stroke="%23383842" stroke-width="2"/><circle cx="50" cy="50" r="28" fill="none" stroke="%2300F0FF" stroke-width="2.5" stroke-dasharray="6,4"/><polygon points="50,32 66,60 34,60" fill="%2300F0FF" opacity="0.8"/></svg>`,
  },
  {
    id: 'neon_nebula',
    name: 'Neon Nebula',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="n" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%238A2BE2"/><stop offset="100%" stop-color="%23FF007F"/></linearGradient></defs><rect width="100" height="100" rx="24" fill="%230A0A10"/><circle cx="50" cy="50" r="30" fill="url(%23n)"/><circle cx="50" cy="50" r="16" fill="%230A0A10"/><circle cx="50" cy="50" r="8" fill="%23FFFFFF"/></svg>`,
  },
  {
    id: 'royal_crest',
    name: 'Royal Crest',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="r" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stop-color="%23D4AF37"/><stop offset="100%" stop-color="%23F3E5AB"/></linearGradient></defs><rect width="100" height="100" rx="24" fill="%23141418"/><path d="M50 20 L76 34 L76 64 C76 78 50 86 50 86 C50 86 24 78 24 64 L24 34 Z" fill="none" stroke="url(%23r)" stroke-width="3"/><circle cx="50" cy="50" r="10" fill="url(%23r)"/></svg>`,
  },
  {
    id: 'minimal_prism',
    name: 'Minimal Prism',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="24" fill="%23121214" stroke="%2326262B" stroke-width="2"/><polygon points="50,22 78,74 22,74" fill="none" stroke="%23E2DFD8" stroke-width="2.5"/><circle cx="50" cy="56" r="6" fill="%23C9A86A"/></svg>`,
  },
];

export default function ProfileModal({ isOpen, onClose }) {
  const user = useAuthStore((s) => s.user);
  const updateProfile = useAuthStore((s) => s.updateProfile);
  const uploadAvatar = useAuthStore((s) => s.uploadAvatar);
  const changePassword = useAuthStore((s) => s.changePassword);

  const [activeTab, setActiveTab] = useState('profile'); // 'profile' | 'security'
  const [name, setName] = useState(user?.name || '');
  const [isSavingName, setIsSavingName] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [copiedId, setCopiedId] = useState(false);
  const [feedback, setFeedback] = useState({ type: null, text: '' });

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  // Email verification resend state
  const [isResendingVerification, setIsResendingVerification] = useState(false);

  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const showNotification = (type, text) => {
    setFeedback({ type, text });
    setTimeout(() => {
      setFeedback({ type: null, text: '' });
    }, 4000);
  };

  const handleCopyUserId = () => {
    if (user?.id) {
      navigator.clipboard.writeText(user.id);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    }
  };

  const handleSaveName = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      showNotification('error', 'Display name cannot be empty.');
      return;
    }

    setIsSavingName(true);
    try {
      await updateProfile({ name: name.trim() });
      showNotification('success', 'Profile name updated successfully.');
    } catch (err) {
      showNotification('error', err.message || 'Failed to update name.');
    } finally {
      setIsSavingName(false);
    }
  };

  const handleSelectPresetAvatar = async (svgData) => {
    setIsUploadingAvatar(true);
    try {
      await updateProfile({ avatar_url: svgData });
      showNotification('success', 'Avatar updated.');
    } catch (err) {
      showNotification('error', err.message || 'Failed to set preset avatar.');
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      showNotification('error', 'Avatar image must be smaller than 5MB.');
      return;
    }

    setIsUploadingAvatar(true);
    try {
      await uploadAvatar(file);
      showNotification('success', 'Profile picture uploaded successfully.');
    } catch (err) {
      showNotification('error', err.message || 'Failed to upload image.');
    } finally {
      setIsUploadingAvatar(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRemoveAvatar = async () => {
    setIsUploadingAvatar(true);
    try {
      await updateProfile({ avatar_url: '' });
      showNotification('success', 'Custom avatar removed.');
    } catch (err) {
      showNotification('error', err.message || 'Failed to remove avatar.');
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();

    if (!currentPassword) {
      showNotification('error', 'Please enter your current password.');
      return;
    }
    if (newPassword.length < 6) {
      showNotification('error', 'New password must be at least 6 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      showNotification('error', 'New passwords do not match.');
      return;
    }

    setIsChangingPassword(true);
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      showNotification('success', 'Password updated successfully!');
    } catch (err) {
      showNotification('error', err.message || 'Failed to update password.');
    } finally {
      setIsChangingPassword(false);
    }
  };

  const handleResendVerification = async () => {
    if (!user?.email) return;
    setIsResendingVerification(true);
    try {
      await authApi.resendVerification(user.email);
      showNotification('success', 'Verification email sent! Check your inbox.');
    } catch (err) {
      showNotification('error', err.message || 'Failed to send verification email.');
    } finally {
      setIsResendingVerification(false);
    }
  };

  const initials = user?.name
    ? user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : user?.email
    ? user.email[0].toUpperCase()
    : 'U';

  const memberSinceFormatted = user?.created_at
    ? new Date(user.created_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Recently';

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4">
      <div className="bg-[#0E0E10] border border-white/[0.08] rounded-3xl max-w-xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-200">
        
        {/* MODAL HEADER */}
        <div className="px-6 pt-6 pb-4 border-b border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-[#C9A86A]/10 border border-[#C9A86A]/30 flex items-center justify-center text-[#C9A86A]">
              <User size={18} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-[#F4F2ED] tracking-tight">Account & Profile</h2>
              <p className="text-xs text-[#8E8B85]">Manage your personal identity, avatar, and security</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-[#7E7B75] hover:text-[#F4F2ED] hover:bg-white/[0.04] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* NOTIFICATION BANNER */}
        {feedback.text && (
          <div
            className={clsx(
              'px-6 py-2.5 flex items-center gap-2 text-xs border-b transition-all',
              feedback.type === 'success'
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
            )}
          >
            {feedback.type === 'success' ? <Check size={14} /> : <AlertCircle size={14} />}
            <span className="font-medium">{feedback.text}</span>
          </div>
        )}

        {/* TABS NAVIGATION */}
        <div className="flex px-6 pt-4 border-b border-white/[0.04] gap-6">
          <button
            onClick={() => setActiveTab('profile')}
            className={clsx(
              'pb-3 text-xs font-semibold tracking-wide transition-all border-b-2 flex items-center gap-2',
              activeTab === 'profile'
                ? 'border-[#C9A86A] text-[#C9A86A]'
                : 'border-transparent text-[#8E8B85] hover:text-[#F4F2ED]'
            )}
          >
            <User size={14} />
            Profile & Identity
          </button>
          <button
            onClick={() => setActiveTab('security')}
            className={clsx(
              'pb-3 text-xs font-semibold tracking-wide transition-all border-b-2 flex items-center gap-2',
              activeTab === 'security'
                ? 'border-[#C9A86A] text-[#C9A86A]'
                : 'border-transparent text-[#8E8B85] hover:text-[#F4F2ED]'
            )}
          >
            <Shield size={14} />
            Security & Password
          </button>
        </div>

        {/* MODAL BODY */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {activeTab === 'profile' && (
            <div className="space-y-6">
              
              {/* AVATAR SECTION */}
              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.05] space-y-4">
                <div className="text-xs font-semibold text-[#DCD9D2] tracking-wider uppercase">
                  Profile Avatar
                </div>

                <div className="flex items-center gap-5">
                  {/* Avatar Preview */}
                  <div className="relative group">
                    <div className="h-20 w-20 rounded-2xl bg-[#141416] border-2 border-[#C9A86A]/40 flex items-center justify-center overflow-hidden shadow-[0_0_20px_rgba(201,168,106,0.15)] shrink-0">
                      {user?.avatar_url ? (
                        <img
                          src={user.avatar_url}
                          alt={user?.name || 'User Avatar'}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <span className="text-2xl font-bold text-[#C9A86A] tracking-wider">
                          {initials}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/png, image/jpeg, image/webp, image/gif, image/svg+xml"
                        className="hidden"
                        onChange={handleFileUpload}
                      />
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploadingAvatar}
                        className="px-3.5 py-1.5 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs transition-all flex items-center gap-1.5 cursor-pointer shadow-sm active:scale-95"
                      >
                        <UploadCloud size={13} />
                        <span>{isUploadingAvatar ? 'Uploading...' : 'Upload Image'}</span>
                      </button>

                      {user?.avatar_url && (
                        <button
                          type="button"
                          onClick={handleRemoveAvatar}
                          disabled={isUploadingAvatar}
                          className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-rose-500/15 text-[#8E8B85] hover:text-rose-400 border border-white/[0.06] hover:border-rose-500/30 text-xs font-medium transition-all flex items-center gap-1.5"
                        >
                          <Trash2 size={13} />
                          <span>Remove</span>
                        </button>
                      )}
                    </div>
                    <p className="text-[11px] text-[#7E7B75] leading-relaxed">
                      Upload JPG, PNG, WebP or SVG up to 5MB, or choose from premium presets below.
                    </p>
                  </div>
                </div>

                {/* PRESET AVATARS PICKER */}
                <div className="space-y-2 pt-2 border-t border-white/[0.04]">
                  <div className="text-[11px] font-medium text-[#8E8B85] flex items-center gap-1.5">
                    <Sparkles size={12} className="text-[#C9A86A]" />
                    <span>Curated Avatars</span>
                  </div>
                  <div className="flex items-center gap-3 overflow-x-auto py-1">
                    {PRESET_AVATARS.map((preset) => {
                      const isSelected = user?.avatar_url === preset.svg;
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectPresetAvatar(preset.svg)}
                          className={clsx(
                            'h-12 w-12 rounded-xl border p-1 transition-all shrink-0 hover:scale-105 active:scale-95 cursor-pointer',
                            isSelected
                              ? 'border-[#C9A86A] ring-2 ring-[#C9A86A]/30 bg-[#C9A86A]/10'
                              : 'border-white/[0.08] hover:border-[#C9A86A]/50 bg-[#121214]'
                          )}
                          title={preset.name}
                        >
                          <img src={preset.svg} alt={preset.name} className="w-full h-full object-contain rounded-lg" />
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* PERSONAL DETAILS FORM */}
              <form onSubmit={handleSaveName} className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.05] space-y-4">
                <div className="text-xs font-semibold text-[#DCD9D2] tracking-wider uppercase">
                  Personal Information
                </div>

                <div className="space-y-3">
                  {/* Display Name Input */}
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-[#8E8B85]">Full / Display Name</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Your full name"
                        className="flex-1 bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/60 rounded-xl px-3.5 py-2 text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors"
                      />
                      <button
                        type="submit"
                        disabled={isSavingName || name.trim() === (user?.name || '')}
                        className={clsx(
                          'px-4 py-2 rounded-xl font-semibold text-xs transition-all flex items-center gap-1.5',
                          name.trim() !== (user?.name || '')
                            ? 'bg-[#C9A86A] text-black hover:bg-[#E1C27A] cursor-pointer shadow-md'
                            : 'bg-white/[0.05] text-[#605D57] cursor-not-allowed'
                        )}
                      >
                        {isSavingName ? <RefreshCw size={13} className="animate-spin" /> : <Check size={13} />}
                        Save
                      </button>
                    </div>
                  </div>

                  {/* Email & Verification Status */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-medium text-[#8E8B85]">Email Address</label>
                      {user?.is_verified ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                          <CheckCircle2 size={10} /> Verified
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
                          <AlertCircle size={10} /> Unverified
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between bg-[#121214] border border-white/[0.06] rounded-xl px-3.5 py-2 text-xs text-[#A09D96]">
                      <div className="flex items-center gap-2 truncate">
                        <Mail size={13} className="text-[#605D57] shrink-0" />
                        <span className="truncate">{user?.email || 'user@example.com'}</span>
                      </div>

                      {!user?.is_verified && (
                        <button
                          type="button"
                          onClick={handleResendVerification}
                          disabled={isResendingVerification}
                          className="text-[11px] text-[#C9A86A] hover:text-[#E1C27A] font-medium transition-colors shrink-0 ml-2"
                        >
                          {isResendingVerification ? 'Sending...' : 'Resend Email'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Metadata: User ID & Created Date */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                    <div className="bg-[#121214] border border-white/[0.04] p-3 rounded-xl space-y-1">
                      <div className="text-[10px] text-[#7E7B75] uppercase tracking-wider flex items-center gap-1">
                        <Fingerprint size={11} /> User ID
                      </div>
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[11px] font-mono text-[#DCD9D2] truncate">
                          {user?.id ? `${user.id.slice(0, 14)}...` : 'N/A'}
                        </span>
                        <button
                          type="button"
                          onClick={handleCopyUserId}
                          className="p-1 rounded text-[#7E7B75] hover:text-[#F4F2ED] transition-colors"
                          title="Copy User ID"
                        >
                          {copiedId ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                        </button>
                      </div>
                    </div>

                    <div className="bg-[#121214] border border-white/[0.04] p-3 rounded-xl space-y-1">
                      <div className="text-[10px] text-[#7E7B75] uppercase tracking-wider flex items-center gap-1">
                        <Calendar size={11} /> Member Since
                      </div>
                      <div className="text-[11px] text-[#DCD9D2] font-medium">
                        {memberSinceFormatted}
                      </div>
                    </div>
                  </div>
                </div>
              </form>
            </div>
          )}

          {activeTab === 'security' && (
            <form onSubmit={handleChangePassword} className="space-y-5">
              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.05] space-y-4">
                <div className="text-xs font-semibold text-[#DCD9D2] tracking-wider uppercase flex items-center gap-1.5">
                  <Lock size={13} className="text-[#C9A86A]" />
                  Change Password
                </div>
                <p className="text-xs text-[#8E8B85] leading-relaxed">
                  Ensure your account uses a strong password of at least 6 characters.
                </p>

                <div className="space-y-3 pt-1">
                  {/* Current Password */}
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-[#8E8B85]">Current Password</label>
                    <div className="relative">
                      <input
                        type={showCurrentPassword ? 'text' : 'password'}
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/60 rounded-xl px-3.5 py-2.5 text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                        className="absolute right-3 top-2.5 text-[#7E7B75] hover:text-[#F4F2ED] transition-colors"
                      >
                        {showCurrentPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* New Password */}
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-[#8E8B85]">New Password</label>
                    <div className="relative">
                      <input
                        type={showNewPassword ? 'text' : 'password'}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Minimum 6 characters"
                        className="w-full bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/60 rounded-xl px-3.5 py-2.5 text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        className="absolute right-3 top-2.5 text-[#7E7B75] hover:text-[#F4F2ED] transition-colors"
                      >
                        {showNewPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* Confirm Password */}
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-[#8E8B85]">Confirm New Password</label>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Repeat new password"
                      className="w-full bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/60 rounded-xl px-3.5 py-2.5 text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors"
                    />
                  </div>

                  {/* Password Match Indicator */}
                  {newPassword && confirmPassword && (
                    <div
                      className={clsx(
                        'text-[11px] flex items-center gap-1.5 pt-1 font-medium',
                        newPassword === confirmPassword ? 'text-emerald-400' : 'text-rose-400'
                      )}
                    >
                      {newPassword === confirmPassword ? <Check size={12} /> : <AlertCircle size={12} />}
                      <span>{newPassword === confirmPassword ? 'Passwords match' : 'Passwords do not match'}</span>
                    </div>
                  )}
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={isChangingPassword || !currentPassword || !newPassword || newPassword !== confirmPassword}
                    className={clsx(
                      'w-full py-2.5 rounded-xl font-semibold text-xs tracking-wider uppercase transition-all flex items-center justify-center gap-2',
                      currentPassword && newPassword && newPassword === confirmPassword && !isChangingPassword
                        ? 'bg-[#C9A86A] text-black hover:bg-[#E1C27A] cursor-pointer shadow-lg shadow-[#C9A86A]/10 active:scale-[0.98]'
                        : 'bg-white/[0.04] text-[#605D57] cursor-not-allowed'
                    )}
                  >
                    {isChangingPassword && <RefreshCw size={13} className="animate-spin" />}
                    <span>{isChangingPassword ? 'Updating Password...' : 'Update Password'}</span>
                  </button>
                </div>
              </div>
            </form>
          )}
        </div>

        {/* MODAL FOOTER */}
        <div className="px-6 py-4 bg-[#0A0A0C] border-t border-white/[0.05] flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl border border-white/[0.08] hover:bg-white/[0.04] text-xs font-medium text-[#A09D96] hover:text-[#F4F2ED] transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
}
