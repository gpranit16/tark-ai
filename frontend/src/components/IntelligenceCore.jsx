import React, { memo } from 'react';
import clsx from 'clsx';

/**
 * IntelligenceCore - Signature TARK AI ambient intelligence visual.
 * 
 * Used for:
 * - Loading / thinking states
 * - Deep research progress
 * - Page empty states (Knowledge, Projects, Memory, Tools)
 * - Refined hero companion
 * 
 * Features:
 * - Subtle concentric orbital rings with slow rotation
 * - Tiny champagne nodes & particles
 * - Soft central radial glow
 * - Pure CSS/SVG, ultra-lightweight, zero WebGL/3D overhead
 */
function IntelligenceCore({ size = 'md', className = '', active = false, label = '' }) {
  const sizeMap = {
    sm: { box: 'w-16 h-16', r1: 18, r2: 26, r3: 31, core: 4 },
    md: { box: 'w-24 h-24', r1: 26, r2: 38, r3: 45, core: 5 },
    lg: { box: 'w-36 h-36', r1: 38, r2: 56, r3: 68, core: 7 },
  };

  const dim = sizeMap[size] || sizeMap.md;

  return (
    <div className={clsx('relative flex flex-col items-center justify-center select-none pointer-events-none', className)}>
      <div className={clsx('relative flex items-center justify-center', dim.box)}>
        {/* Soft Radial Ambient Illumination */}
        <div
          className={clsx(
            'absolute inset-0 rounded-full blur-xl transition-opacity duration-700',
            active ? 'bg-accent/15 opacity-80' : 'bg-accent/8 opacity-40'
          )}
        />

        {/* SVG Orbital Circles & Sparse Nodes */}
        <svg
          viewBox="0 0 100 100"
          className={clsx(
            'w-full h-full text-accent',
            active ? 'animate-orbit-slow' : ''
          )}
          fill="none"
        >
          {/* Outer Orbital Ring */}
          <circle
            cx="50"
            cy="50"
            r={dim.r3}
            stroke="rgba(201, 168, 106, 0.12)"
            strokeWidth="0.75"
            strokeDasharray="4 6"
          />

          {/* Middle Orbital Ring */}
          <circle
            cx="50"
            cy="50"
            r={dim.r2}
            stroke="rgba(201, 168, 106, 0.18)"
            strokeWidth="0.75"
          />

          {/* Inner Orbital Ring */}
          <circle
            cx="50"
            cy="50"
            r={dim.r1}
            stroke="rgba(201, 168, 106, 0.10)"
            strokeWidth="0.5"
            strokeDasharray="2 4"
          />

          {/* Sparse Orbital Nodes */}
          <circle
            cx={50 + dim.r2 * 0.85}
            cy={50 - dim.r2 * 0.52}
            r="1.5"
            fill="#E1C27A"
            opacity={active ? '0.9' : '0.6'}
            className="animate-subtle-pulse"
          />
          <circle
            cx={50 - dim.r1 * 0.7}
            cy={50 + dim.r1 * 0.7}
            r="1.2"
            fill="#C9A86A"
            opacity={active ? '0.8' : '0.45'}
          />
          <circle
            cx={50 + dim.r3 * 0.3}
            cy={50 + dim.r3 * 0.95}
            r="1"
            fill="#8E7548"
            opacity="0.35"
          />

          {/* Central Core */}
          <circle
            cx="50"
            cy="50"
            r={dim.core}
            fill="url(#coreGradient)"
            className={clsx(active && 'animate-subtle-pulse')}
          />

          <defs>
            <radialGradient id="coreGradient" cx="40%" cy="40%" r="60%">
              <stop offset="0%" stopColor="#FFF2D6" stopOpacity="0.95" />
              <stop offset="45%" stopColor="#C9A86A" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#8E7548" stopOpacity="0.2" />
            </radialGradient>
          </defs>
        </svg>
      </div>

      {label && (
        <span className="text-[11px] font-medium text-[#77736D] tracking-wider uppercase mt-2">
          {label}
        </span>
      )}
    </div>
  );
}

export default memo(IntelligenceCore);
