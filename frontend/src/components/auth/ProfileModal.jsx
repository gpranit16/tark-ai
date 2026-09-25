import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
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
  Camera,
} from 'lucide-react';
import clsx from 'clsx';
import { useAuthStore } from '../../stores/useAuthStore';
import { authApi } from '../../api/authApi';

// 10 Curated Luxury Preset Avatars for TARK AI
const PRESET_AVATARS = [
  {
    id: 'gold_core',
    name: 'TARK Gold Core',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="g" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="%23FFE6A3"/><stop offset="50%" stop-color="%23C9A86A"/><stop offset="100%" stop-color="%2318140E"/></radialGradient></defs><rect width="100" height="100" rx="28" fill="%230E0E10"/><circle cx="50" cy="50" r="34" fill="url(%23g)" stroke="%23FFE6A3" stroke-width="2.5"/><path d="M50 24 L57 43 L76 50 L57 57 L50 76 L43 57 L24 50 L43 43 Z" fill="%23FFFFFF" opacity="0.95"/></svg>`,
  },
  {
    id: 'cyber_obsidian',
    name: 'Cyber Obsidian',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="o" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%232A2A30"/><stop offset="100%" stop-color="%2308080A"/></linearGradient></defs><rect width="100" height="100" rx="28" fill="url(%23o)" stroke="%23383842" stroke-width="2"/><circle cx="50" cy="50" r="30" fill="none" stroke="%2300F0FF" stroke-width="2.5" stroke-dasharray="6,4"/><polygon points="50,30 68,62 32,62" fill="%2300F0FF" opacity="0.85"/><circle cx="50" cy="50" r="5" fill="%23FFFFFF"/></svg>`,
  },
  {
    id: 'neon_nebula',
    name: 'Neon Nebula',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="n" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%238A2BE2"/><stop offset="100%" stop-color="%23FF007F"/></linearGradient></defs><rect width="100" height="100" rx="28" fill="%230A0A10"/><circle cx="50" cy="50" r="32" fill="url(%23n)"/><circle cx="50" cy="50" r="18" fill="%230A0A10"/><circle cx="50" cy="50" r="9" fill="%23FFFFFF"/></svg>`,
  },
  {
    id: 'royal_crest',
    name: 'Royal Crest',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="r" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stop-color="%23D4AF37"/><stop offset="100%" stop-color="%23F3E5AB"/></linearGradient></defs><rect width="100" height="100" rx="28" fill="%23141418"/><path d="M50 18 L78 32 L78 64 C78 78 50 86 50 86 C50 86 22 78 22 64 L22 32 Z" fill="none" stroke="url(%23r)" stroke-width="3"/><circle cx="50" cy="46" r="10" fill="url(%23r)"/></svg>`,
  },
  {
    id: 'minimal_prism',
    name: 'Minimal Prism',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="28" fill="%23121214" stroke="%2326262B" stroke-width="2"/><polygon points="50,20 80,74 20,74" fill="none" stroke="%23E2DFD8" stroke-width="2.5"/><circle cx="50" cy="56" r="7" fill="%23C9A86A"/></svg>`,
  },
  {
    id: 'emerald_matrix',
    name: 'Emerald Matrix',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="em" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%2300E676"/><stop offset="100%" stop-color="%23004D40"/></linearGradient></defs><rect width="100" height="100" rx="28" fill="%2306120E"/><polygon points="50,18 82,50 50,82 18,50" fill="none" stroke="url(%23em)" stroke-width="3"/><circle cx="50" cy="50" r="14" fill="url(%23em)" opacity="0.9"/></svg>`,
  },
  {
    id: 'sapphire_nova',
    name: 'Sapphire Nova',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="sn" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="%2300B0FF"/><stop offset="70%" stop-color="%231A237E"/><stop offset="100%" stop-color="%230A0E2A"/></radialGradient></defs><rect width="100" height="100" rx="28" fill="%230A0E1A"/><circle cx="50" cy="50" r="32" fill="url(%23sn)" stroke="%2340C4FF" stroke-width="2"/><path d="M50 28 L54 46 L72 50 L54 54 L50 72 L46 54 L28 50 L46 46 Z" fill="%23FFFFFF"/></svg>`,
  },
  {
    id: 'crimson_phoenix',
    name: 'Crimson Phoenix',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="cp" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stop-color="%23D50000"/><stop offset="60%" stop-color="%23FF6D00"/><stop offset="100%" stop-color="%23FFD600"/></linearGradient></defs><rect width="100" height="100" rx="28" fill="%23140808"/><circle cx="50" cy="50" r="30" fill="none" stroke="url(%23cp)" stroke-width="3"/><polygon points="50,26 65,58 50,50 35,58" fill="url(%23cp)"/><circle cx="50" cy="68" r="4" fill="%23FFD600"/></svg>`,
  },
  {
    id: 'amethyst_monarch',
    name: 'Amethyst Monarch',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="am" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="%23B388FF"/><stop offset="100%" stop-color="%234A148C"/></linearGradient></defs><rect width="100" height="100" rx="28" fill="%230E0814"/><rect x="25" y="25" width="50" height="50" rx="12" transform="rotate(45 50 50)" fill="url(%23am)" stroke="%23D1C4E9" stroke-width="2"/><circle cx="50" cy="50" r="8" fill="%23FFFFFF"/></svg>`,
  },
  {
    id: 'solar_eclipse',
    name: 'Solar Eclipse',
    svg: `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><radialGradient id="se" cx="50%" cy="50%" r="50%"><stop offset="60%" stop-color="%23FFA000"/><stop offset="100%" stop-color="%23FF6F00"/></radialGradient></defs><rect width="100" height="100" rx="28" fill="%230A0A0C"/><circle cx="50" cy="50" r="34" fill="url(%23se)" filter="blur(1px)"/><circle cx="50" cy="50" r="28" fill="%230A0A0C" stroke="%23FFE082" stroke-width="1.5"/></svg>`,
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

  // Synchronize name whenever user object changes
  useEffect(() => {
    if (user?.name) {
      setName(user.name);
    }
  }, [user?.name]);

  // Handle ESC key to close modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

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
      showNotification('success', 'Preset avatar selected.');
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
      showNotification('success', 'Profile picture updated successfully.');
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

  if (!isOpen) return null;
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 bg-black/85 backdrop-blur-md z-[100] flex items-center justify-center p-3 sm:p-5 overflow-y-auto"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-[#0E0E12] border border-white/[0.08] rounded-2xl sm:rounded-3xl max-w-lg w-full shadow-[0_25px_70px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col my-auto max-h-[92vh] sm:max-h-[85vh] animate-in fade-in zoom-in-95 duration-200">
        
        {/* MODAL HEADER */}
        <div className="px-4 sm:px-6 pt-5 pb-3.5 border-b border-white/[0.06] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-[#C9A86A]/10 border border-[#C9A86A]/30 flex items-center justify-center text-[#C9A86A] shrink-0">
              <User size={18} />
            </div>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-[#F4F2ED] tracking-tight truncate">
                Account & Profile
              </h2>
              <p className="text-[11px] sm:text-xs text-[#8E8B85] truncate">
                Manage your avatar, identity, and security
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl text-[#7E7B75] hover:text-[#F4F2ED] hover:bg-white/[0.06] transition-colors shrink-0 cursor-pointer min-w-[36px] min-h-[36px] flex items-center justify-center"
            title="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        {/* NOTIFICATION BANNER */}
        {feedback.text && (
          <div
            className={clsx(
              'px-4 sm:px-6 py-2.5 flex items-center gap-2 text-xs border-b transition-all shrink-0',
              feedback.type === 'success'
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
            )}
          >
            {feedback.type === 'success' ? <Check size={14} className="shrink-0" /> : <AlertCircle size={14} className="shrink-0" />}
            <span className="font-medium truncate">{feedback.text}</span>
          </div>
        )}

        {/* FULLY RESPONSIVE SEGMENTED TABS */}
        <div className="px-4 sm:px-6 pt-3.5 pb-1 shrink-0">
          <div className="grid grid-cols-2 p-1 bg-[#141418] border border-white/[0.06] rounded-xl">
            <button
              type="button"
              onClick={() => setActiveTab('profile')}
              className={clsx(
                'py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer min-h-[36px]',
                activeTab === 'profile'
                  ? 'bg-[#C9A86A] text-black shadow-sm'
                  : 'text-[#8E8B85] hover:text-[#F4F2ED]'
              )}
            >
              <User size={13} />
              <span>Profile & DP</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('security')}
              className={clsx(
                'py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer min-h-[36px]',
                activeTab === 'security'
                  ? 'bg-[#C9A86A] text-black shadow-sm'
                  : 'text-[#8E8B85] hover:text-[#F4F2ED]'
              )}
            >
              <Shield size={13} />
              <span>Security</span>
            </button>
          </div>
        </div>

        {/* MODAL BODY */}
        <div className="p-4 sm:p-6 overflow-y-auto space-y-4 sm:space-y-5 flex-1 overscroll-contain">
          {activeTab === 'profile' && (
            <div className="space-y-4 sm:space-y-5">
              
              {/* AVATAR & DP SECTION */}
              <div className="p-3.5 sm:p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-[#DCD9D2] tracking-wider uppercase">
                    Profile Avatar / DP
                  </span>
                  <span className="text-[10px] text-[#7E7B75] hidden xs:inline">
                    Tap photo to change
                  </span>
                </div>

                {/* Avatar Preview & Actions Container */}
                <div className="flex flex-col xs:flex-row items-center xs:items-start gap-4 sm:gap-5">
                  {/* Clickable Avatar Photo */}
                  <div className="relative group shrink-0">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploadingAvatar}
                      title="Click or tap to change photo"
                      className="relative h-20 w-20 sm:h-22 sm:w-22 rounded-2xl bg-[#141416] border-2 border-[#C9A86A]/50 hover:border-[#C9A86A] flex items-center justify-center overflow-hidden shadow-[0_0_20px_rgba(201,168,106,0.18)] transition-all cursor-pointer group-hover:scale-[1.02] active:scale-95"
                    >
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

                      {/* Desktop Hover Overlay */}
                      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center gap-1 text-[#F4F2ED] transition-opacity duration-200">
                        {isUploadingAvatar ? (
                          <RefreshCw size={18} className="animate-spin text-[#C9A86A]" />
                        ) : (
                          <>
                            <Camera size={18} className="text-[#C9A86A]" />
                            <span className="text-[10px] font-semibold tracking-tight">Change</span>
                          </>
                        )}
                      </div>

                      {/* Loading state indicator */}
                      {isUploadingAvatar && (
                        <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
                          <RefreshCw size={20} className="animate-spin text-[#C9A86A]" />
                        </div>
                      )}
                    </button>

                    {/* Touch / Mobile Camera Badge */}
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="absolute -bottom-1 -right-1 h-7 w-7 rounded-full bg-[#C9A86A] hover:bg-[#E1C27A] text-black shadow-md flex items-center justify-center border-2 border-[#0D0D10] transition-transform active:scale-90 cursor-pointer"
                      title="Upload new picture"
                    >
                      <Camera size={13} strokeWidth={2.5} />
                    </button>
                  </div>

                  {/* Actions & File upload triggers */}
                  <div className="space-y-2.5 flex-1 w-full text-center xs:text-left">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png, image/jpeg, image/webp, image/gif, image/svg+xml"
                      className="hidden"
                      onChange={handleFileUpload}
                    />
                    
                    <div className="flex items-center justify-center xs:justify-start gap-2 flex-wrap">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploadingAvatar}
                        className="px-3.5 py-2 rounded-xl bg-[#C9A86A] hover:bg-[#E1C27A] text-black font-semibold text-xs transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-sm active:scale-95 min-h-[38px] flex-1 xs:flex-none"
                      >
                        <UploadCloud size={14} />
                        <span>{isUploadingAvatar ? 'Updating...' : 'Upload Image'}</span>
                      </button>

                      {user?.avatar_url && (
                        <button
                          type="button"
                          onClick={handleRemoveAvatar}
                          disabled={isUploadingAvatar}
                          className="px-3 py-2 rounded-xl bg-white/[0.04] hover:bg-rose-500/15 text-[#8E8B85] hover:text-rose-400 border border-white/[0.06] hover:border-rose-500/30 text-xs font-medium transition-all flex items-center justify-center gap-1.5 cursor-pointer min-h-[38px]"
                          title="Remove custom photo"
                        >
                          <Trash2 size={13} />
                          <span>Remove</span>
                        </button>
                      )}
                    </div>

                    <p className="text-[11px] text-[#7E7B75] leading-relaxed">
                      Upload JPG, PNG, WebP or SVG up to 5MB, or choose from the curated presets below.
                    </p>
                  </div>
                </div>

                {/* 10 CURATED PRESET AVATARS CAROUSEL */}
                <div className="space-y-2 pt-3 border-t border-white/[0.04]">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] font-medium text-[#8E8B85] flex items-center gap-1.5">
                      <Sparkles size={12} className="text-[#C9A86A]" />
                      <span>Curated Luxury Avatars</span>
                    </div>
                    <span className="text-[10px] text-[#C9A86A]/80 font-mono">10 Presets</span>
                  </div>

                  <div className="flex items-center gap-2.5 overflow-x-auto pb-1.5 pt-1 scrollbar-thin snap-x">
                    {PRESET_AVATARS.map((preset) => {
                      const isSelected = user?.avatar_url === preset.svg;
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectPresetAvatar(preset.svg)}
                          disabled={isUploadingAvatar}
                          className={clsx(
                            'relative h-12 w-12 sm:h-13 sm:w-13 rounded-xl border p-1 transition-all shrink-0 cursor-pointer snap-start',
                            isSelected
                              ? 'border-[#C9A86A] ring-2 ring-[#C9A86A] bg-[#C9A86A]/20 scale-105 shadow-[0_0_12px_rgba(201,168,106,0.3)]'
                              : 'border-white/[0.08] hover:border-[#C9A86A]/60 bg-[#121214] hover:scale-105 active:scale-95'
                          )}
                          title={preset.name}
                        >
                          <img
                            src={preset.svg}
                            alt={preset.name}
                            className="w-full h-full object-contain rounded-lg"
                          />
                          {isSelected && (
                            <span className="absolute -top-1 -right-1 h-4 w-4 bg-[#C9A86A] text-black rounded-full flex items-center justify-center shadow">
                              <Check size={10} strokeWidth={3} />
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* PERSONAL INFORMATION FORM */}
              <form
                onSubmit={handleSaveName}
                className="p-3.5 sm:p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] space-y-3.5"
              >
                <div className="text-[11px] font-semibold text-[#DCD9D2] tracking-wider uppercase">
                  Personal Information
                </div>

                <div className="space-y-3">
                  {/* Display Name Input */}
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-[#8E8B85]">
                      Full / Display Name
                    </label>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Your full name"
                        className="flex-1 bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/70 rounded-xl px-3.5 py-2.5 text-sm sm:text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors"
                      />
                      <button
                        type="submit"
                        disabled={isSavingName || name.trim() === (user?.name || '')}
                        className={clsx(
                          'px-4 py-2.5 rounded-xl font-semibold text-xs transition-all flex items-center justify-center gap-1.5 min-h-[40px]',
                          name.trim() !== (user?.name || '')
                            ? 'bg-[#C9A86A] text-black hover:bg-[#E1C27A] cursor-pointer shadow-md'
                            : 'bg-white/[0.04] text-[#605D57] cursor-not-allowed'
                        )}
                      >
                        {isSavingName ? (
                          <RefreshCw size={13} className="animate-spin" />
                        ) : (
                          <Check size={13} />
                        )}
                        <span>Save Name</span>
                      </button>
                    </div>
                  </div>

                  {/* Email & Verification Status */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-medium text-[#8E8B85]">
                        Email Address
                      </label>
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

                    <div className="flex flex-col xs:flex-row xs:items-center justify-between gap-2 bg-[#121214] border border-white/[0.06] rounded-xl px-3.5 py-2.5 text-xs text-[#A09D96]">
                      <div className="flex items-center gap-2 truncate min-w-0">
                        <Mail size={14} className="text-[#605D57] shrink-0" />
                        <span className="truncate text-[#E2DFD8]">{user?.email || 'user@example.com'}</span>
                      </div>

                      {!user?.is_verified && (
                        <button
                          type="button"
                          onClick={handleResendVerification}
                          disabled={isResendingVerification}
                          className="self-end xs:self-auto text-[11px] text-[#C9A86A] hover:text-[#E1C27A] font-medium transition-colors shrink-0 cursor-pointer"
                        >
                          {isResendingVerification ? 'Sending...' : 'Resend Verification'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Metadata: User ID & Created Date */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
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
                          className="p-1 rounded text-[#7E7B75] hover:text-[#F4F2ED] transition-colors cursor-pointer"
                          title="Copy User ID"
                        >
                          {copiedId ? (
                            <Check size={12} className="text-emerald-400" />
                          ) : (
                            <Copy size={12} />
                          )}
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
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="p-3.5 sm:p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] space-y-3.5">
                <div className="text-[11px] font-semibold text-[#DCD9D2] tracking-wider uppercase flex items-center gap-1.5">
                  <Lock size={13} className="text-[#C9A86A]" />
                  <span>Update Account Password</span>
                </div>
                <p className="text-xs text-[#8E8B85] leading-relaxed">
                  Use a secure password with a minimum of 6 characters to safeguard your conversations and keys.
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
                        className="w-full bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/70 rounded-xl px-3.5 py-2.5 text-sm sm:text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors pr-10 min-h-[42px]"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                        className="absolute right-2.5 top-2.5 p-1 text-[#7E7B75] hover:text-[#F4F2ED] transition-colors cursor-pointer"
                        title={showCurrentPassword ? 'Hide password' : 'Show password'}
                      >
                        {showCurrentPassword ? <EyeOff size={15} /> : <Eye size={15} />}
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
                        className="w-full bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/70 rounded-xl px-3.5 py-2.5 text-sm sm:text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors pr-10 min-h-[42px]"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        className="absolute right-2.5 top-2.5 p-1 text-[#7E7B75] hover:text-[#F4F2ED] transition-colors cursor-pointer"
                        title={showNewPassword ? 'Hide password' : 'Show password'}
                      >
                        {showNewPassword ? <EyeOff size={15} /> : <Eye size={15} />}
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
                      className="w-full bg-[#121214] border border-white/[0.08] focus:border-[#C9A86A]/70 rounded-xl px-3.5 py-2.5 text-sm sm:text-xs text-[#F4F2ED] placeholder-[#605D57] outline-none transition-colors min-h-[42px]"
                    />
                  </div>

                  {/* Password Match Indicator */}
                  {newPassword && confirmPassword && (
                    <div
                      className={clsx(
                        'text-[11px] flex items-center gap-1.5 pt-0.5 font-medium',
                        newPassword === confirmPassword ? 'text-emerald-400' : 'text-rose-400'
                      )}
                    >
                      {newPassword === confirmPassword ? (
                        <Check size={13} className="shrink-0" />
                      ) : (
                        <AlertCircle size={13} className="shrink-0" />
                      )}
                      <span>
                        {newPassword === confirmPassword
                          ? 'Passwords match'
                          : 'Passwords do not match'}
                      </span>
                    </div>
                  )}
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={
                      isChangingPassword ||
                      !currentPassword ||
                      !newPassword ||
                      newPassword !== confirmPassword
                    }
                    className={clsx(
                      'w-full py-2.5 px-4 rounded-xl font-semibold text-xs tracking-wider uppercase transition-all flex items-center justify-center gap-2 min-h-[42px]',
                      currentPassword &&
                        newPassword &&
                        newPassword === confirmPassword &&
                        !isChangingPassword
                        ? 'bg-[#C9A86A] text-black hover:bg-[#E1C27A] cursor-pointer shadow-lg shadow-[#C9A86A]/15 active:scale-[0.98]'
                        : 'bg-white/[0.04] text-[#605D57] cursor-not-allowed'
                    )}
                  >
                    {isChangingPassword && <RefreshCw size={13} className="animate-spin" />}
                    <span>{isChangingPassword ? 'Updating Password...' : 'Save New Password'}</span>
                  </button>
                </div>
              </div>
            </form>
          )}
        </div>

        {/* MODAL FOOTER */}
        <div className="px-4 sm:px-6 py-3.5 bg-[#0A0A0C] border-t border-white/[0.05] flex items-center justify-between shrink-0">
          <div className="text-[11px] text-[#7E7B75] truncate max-w-[180px] xs:max-w-xs">
            {user?.name || user?.email || 'TARK AI'}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl border border-white/[0.08] hover:bg-white/[0.06] text-xs font-medium text-[#A09D96] hover:text-[#F4F2ED] transition-colors cursor-pointer min-h-[36px]"
          >
            Done
          </button>
        </div>

      </div>
    </div>,
    document.body
  );
}
