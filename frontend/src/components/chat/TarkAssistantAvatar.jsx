import React, { memo } from 'react';

/**
 * TarkAssistantAvatar - Signature Gold & Obsidian Assistant Emblem for TARK AI
 * 
 * Target size: 40-42px circular badge
 * T symbol: ~24-26px visual height (~60% of badge)
 * Colors: Obsidian (#111111) base with champagne gold (#D8AA32 -> #F0C85A)
 */
function TarkAssistantAvatar({ size = 40, className = '' }) {
  return (
    <div
      className={`relative shrink-0 rounded-full flex items-center justify-center select-none ${className}`}
      style={{
        width: size,
        height: size,
        minWidth: size,
        minHeight: size,
      }}
      aria-hidden="true"
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 44 44"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full drop-shadow-[0_2px_8px_rgba(216,170,50,0.18)]"
      >
        <defs>
          {/* Obsidian Base Gradient */}
          <radialGradient id="tarkAvatarBg" cx="38%" cy="32%" r="65%" fx="38%" fy="32%">
            <stop offset="0%" stopColor="#1e1e24" />
            <stop offset="60%" stopColor="#121215" />
            <stop offset="100%" stopColor="#0a0a0c" />
          </radialGradient>

          {/* Warm Champagne Gold Metallic Gradient for T and Rim */}
          <linearGradient id="tarkGoldMetallic" x1="8" y1="8" x2="36" y2="36" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#F5D77F" />
            <stop offset="35%" stopColor="#E0B746" />
            <stop offset="70%" stopColor="#D8AA32" />
            <stop offset="100%" stopColor="#B3841D" />
          </linearGradient>

          {/* Highlight Gold Gradient */}
          <linearGradient id="tarkGoldHighlight" x1="12" y1="10" x2="32" y2="34" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFF2B8" />
            <stop offset="40%" stopColor="#F0C85A" />
            <stop offset="100%" stopColor="#C99726" />
          </linearGradient>

          {/* Subtle Outer Rim Bevel Gradient */}
          <linearGradient id="tarkRimBevel" x1="6" y1="6" x2="38" y2="38" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#F0C85A" stopOpacity="0.85" />
            <stop offset="45%" stopColor="#D8AA32" stopOpacity="0.5" />
            <stop offset="80%" stopColor="#8A6714" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#F0C85A" stopOpacity="0.6" />
          </linearGradient>

          {/* Subtle Inner Glow Filter */}
          <filter id="tarkInnerBloom" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur stdDeviation="0.6" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Outer Circular Rim with Gold Metallic Stroke */}
        <circle
          cx="22"
          cy="22"
          r="20"
          fill="url(#tarkAvatarBg)"
          stroke="url(#tarkRimBevel)"
          strokeWidth="1.25"
        />

        {/* Fine Inner Accent Ring */}
        <circle
          cx="22"
          cy="22"
          r="18.2"
          stroke="url(#tarkGoldMetallic)"
          strokeWidth="0.5"
          strokeOpacity="0.3"
        />

        {/* TARK Signature Orbital Swirl Arc (Matches Brand Emblem) */}
        <path
          d="M 10 26 C 9 17, 16 10, 24 10.5 C 31 11, 35 17, 34 22 C 33 27, 28 34, 18 34 C 13.5 34, 11 31, 10 26"
          stroke="url(#tarkGoldHighlight)"
          strokeWidth="1.1"
          strokeLinecap="round"
          fill="none"
          opacity="0.75"
        />

        {/* Main Geometric TARK 'T' Symbol */}
        <g filter="url(#tarkInnerBloom)">
          {/* T Crossbar */}
          <path
            d="M 12.5 13.5 C 12.5 13 13 12.5 13.5 12.5 H 30.5 C 31 12.5 31.5 13 31.5 13.5 V 17.5 C 31.5 17.8 31.2 18 30.8 18 H 24.8 V 30 C 24.8 30.6 24.3 31 23.7 31 H 20.3 C 19.7 31 19.2 30.6 19.2 30 V 18 H 13.2 C 12.8 18 12.5 17.8 12.5 17.5 Z"
            fill="url(#tarkGoldMetallic)"
          />

          {/* T Top Bevel Highlight */}
          <path
            d="M 13.5 13 H 30.5 C 31 13 31.2 13.2 31.2 13.5 V 14.5 H 12.8 V 13.5 C 12.8 13.2 13 13 13.5 13 Z"
            fill="url(#tarkGoldHighlight)"
            opacity="0.8"
          />

          {/* T Stem Left Edge Subtle Highlight */}
          <rect
            x="19.2"
            y="18"
            width="1.2"
            height="12"
            fill="url(#tarkGoldHighlight)"
            opacity="0.55"
          />
        </g>

        {/* Small Precision Orbital Accent Spark */}
        <circle
          cx="33.8"
          cy="20.5"
          r="0.9"
          fill="#FFF4D0"
          opacity="0.9"
        />
      </svg>
    </div>
  );
}

export default memo(TarkAssistantAvatar);
