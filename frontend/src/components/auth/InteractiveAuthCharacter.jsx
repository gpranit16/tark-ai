import React, { useEffect, useState, useMemo, useRef } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';

/**
 * InteractiveAuthCharacter (TARK AI Companion Robot Mascot)
 * 
 * Large, premium, futuristic companion robot:
 * - Dynamic 2D cursor tracking: Robot head & glowing eyes follow mouse movement across screen
 * - Centered luxury editorial greeting typography positioned directly above robot head/antenna
 * - Rounded pearlescent ivory/white mechanical body
 * - Large glossy obsidian face display
 * - Glowing warm gold expressive OLED eyes
 * - Mechanical ear sensors with champagne loops & glowing beacon antenna
 * - Subtle floating pedestal light ring
 * - Reactive state machine driving postures, eye shapes, gaze tracking & privacy mode
 */
export default function InteractiveAuthCharacter({
  focusedField = 'none', // 'none' | 'name' | 'email' | 'password' | 'confirmPassword'
  isPasswordVisible = false,
  authStatus = 'idle', // 'idle' | 'loading' | 'success' | 'error'
  formMode = 'login', // 'login' | 'signup' | 'forgot'
  inputLength = 0,
}) {
  const shouldReduceMotion = useReducedMotion();
  const [isBlinking, setIsBlinking] = useState(false);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);

  // Derive explicit robot state from props
  const robotState = useMemo(() => {
    if (authStatus === 'success') return 'success';
    if (authStatus === 'error') return 'error';

    const isPasswordField = focusedField === 'password' || focusedField === 'confirmPassword';
    if (isPasswordField) {
      if (isPasswordVisible) return 'passwordVisible';
      if (inputLength > 0) return 'passwordTyping';
      return 'passwordFocus';
    }

    if (focusedField === 'email' || focusedField === 'name') {
      return 'emailFocus';
    }

    if (formMode === 'signup') {
      return 'signup';
    }

    return 'idle';
  }, [authStatus, focusedField, isPasswordVisible, inputLength, formMode]);

  // Cursor movement tracking (smoothly follow cursor anywhere on screen)
  useEffect(() => {
    if (shouldReduceMotion) return;

    const handleMouseMove = (e) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height * 0.38; // Robot head center

      const deltaX = (e.clientX - centerX) / (window.innerWidth * 0.5);
      const deltaY = (e.clientY - centerY) / (window.innerHeight * 0.5);

      const clampedX = Math.max(-1, Math.min(1, deltaX));
      const clampedY = Math.max(-1, Math.min(1, deltaY));

      setMousePos({ x: clampedX, y: clampedY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [shouldReduceMotion]);

  // Organic idle eye blinking (disabled during privacy mode or error)
  useEffect(() => {
    if (robotState === 'passwordFocus' || robotState === 'passwordTyping') {
      setIsBlinking(false);
      return;
    }

    let blinkTimeout;
    const interval = setInterval(() => {
      setIsBlinking(true);
      blinkTimeout = setTimeout(() => setIsBlinking(false), 160);
    }, 4000 + Math.random() * 2600);

    return () => {
      clearInterval(interval);
      clearTimeout(blinkTimeout);
    };
  }, [robotState]);

  // Eye Gaze Offset (combining state + dynamic cursor tracking)
  const gazeOffset = useMemo(() => {
    if (shouldReduceMotion) return { x: 0, y: 0 };

    switch (robotState) {
      case 'passwordFocus':
      case 'passwordTyping':
        // Respect privacy — eyes are closed, no cursor gaze
        return { x: 0, y: 0 };

      case 'emailFocus': {
        const charShift = Math.min(inputLength * 0.25, 4.5);
        return {
          x: 5 + charShift + mousePos.x * 2.5,
          y: 1.5 + mousePos.y * 3,
        };
      }

      case 'passwordVisible':
        return {
          x: 5 + mousePos.x * 3,
          y: 1.5 + mousePos.y * 3,
        };

      case 'error':
        return {
          x: -2 + mousePos.x * 2,
          y: -1 + mousePos.y * 2,
        };

      case 'success':
        return {
          x: mousePos.x * 2,
          y: -2 + mousePos.y * 2,
        };

      case 'signup':
        return {
          x: 2 + mousePos.x * 6,
          y: mousePos.y * 4.5,
        };

      case 'idle':
      default:
        // Free organic cursor tracking
        return {
          x: mousePos.x * 8.5,
          y: mousePos.y * 6.5,
        };
    }
  }, [robotState, inputLength, mousePos, shouldReduceMotion]);

  // Head and body transform (combining state + dynamic cursor tracking)
  const headTransform = useMemo(() => {
    if (shouldReduceMotion) return { rotate: 0, x: 0, y: 0 };

    switch (robotState) {
      case 'passwordFocus':
      case 'passwordTyping':
        // Polite privacy posture — head calmly bowed down
        return { rotate: -1.5, x: -2, y: 3 };

      case 'emailFocus':
        return {
          rotate: 2.2 + mousePos.x * 2,
          x: 4 + mousePos.x * 3,
          y: 1 + mousePos.y * 2,
        };

      case 'passwordVisible':
        return {
          rotate: 1.8 + mousePos.x * 2.5,
          x: 3 + mousePos.x * 3,
          y: mousePos.y * 2,
        };

      case 'error':
        return {
          rotate: -3.5 + mousePos.x * 1.5,
          x: -3 + mousePos.x * 2,
          y: 1 + mousePos.y * 2,
        };

      case 'success':
        return {
          rotate: mousePos.x * 2,
          x: mousePos.x * 2,
          y: -4 + mousePos.y * 2,
        };

      case 'signup':
        return {
          rotate: 1.2 + mousePos.x * 3,
          x: 2 + mousePos.x * 4,
          y: -1 + mousePos.y * 2.5,
        };

      case 'idle':
      default:
        // Fluid head orientation following cursor
        return {
          rotate: mousePos.x * 8.5,
          x: mousePos.x * 7,
          y: mousePos.y * 4.5,
        };
    }
  }, [robotState, mousePos, shouldReduceMotion]);

  // Editorial Greeting Typography (Centered directly above robot)
  const greetingText = useMemo(() => {
    switch (robotState) {
      case 'passwordFocus':
      case 'passwordTyping':
        return {
          title: "I'll keep this private.",
          symbol: "🔒",
        };
      case 'passwordVisible':
        return {
          title: "Eyes open.",
          symbol: "✦",
        };
      case 'error':
        return {
          title: "Double-check credentials.",
          symbol: "✦",
        };
      case 'success':
        return {
          title: "Welcome to TARK AI.",
          symbol: "✨",
        };
      case 'signup':
        return {
          title: "Welcome to TARK AI.",
          symbol: "✦",
        };
      case 'emailFocus':
        return {
          title: inputLength > 0 ? "Ready when you are." : "Good to see you again.",
          symbol: "✦",
        };
      case 'idle':
      default:
        return {
          title: "Good to see you again.",
          symbol: "✦",
        };
    }
  }, [robotState, inputLength]);

  const isEyesClosed =
    isBlinking ||
    robotState === 'passwordFocus' ||
    robotState === 'passwordTyping';

  return (
    <div
      ref={containerRef}
      className="relative w-full max-w-[380px] sm:max-w-[440px] lg:max-w-[480px] aspect-[4/5] flex items-center justify-center select-none pointer-events-none"
    >
      {/* ── BACKGROUND AMBIENT GLOW ─────────────────────────────── */}
      <motion.div
        animate={{
          scale: robotState === 'success' ? [1, 1.15, 1.05] : [1, 1.04, 1],
          opacity: robotState === 'success' ? 0.35 : robotState.startsWith('password') ? 0.12 : 0.22,
        }}
        transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute w-[85%] h-[85%] rounded-full bg-[radial-gradient(circle,rgba(201,168,106,0.35)_0%,rgba(201,168,106,0.08)_45%,transparent_70%)] blur-2xl pointer-events-none"
      />

      {/* ── TOP EDITORIAL GREETING (CENTERED DIRECTLY ABOVE ROBOT HEAD) ─── */}
      <div className="absolute top-1 sm:top-2 lg:top-2.5 left-1/2 -translate-x-1/2 z-20 pointer-events-none whitespace-nowrap flex justify-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={greetingText.title}
            initial={{ opacity: 0, y: 5, filter: 'blur(3px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -4, filter: 'blur(3px)' }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="flex items-center gap-2.5 select-none"
          >
            <span className="text-[#E5C378] text-base sm:text-lg leading-none drop-shadow-[0_0_10px_rgba(201,168,106,0.45)]">
              {greetingText.symbol}
            </span>
            <span className="font-serif italic text-xl sm:text-2xl lg:text-[23px] font-normal tracking-wide bg-gradient-to-r from-[#FFF8E7] via-[#E8C87E] to-[#C9A86A] bg-clip-text text-transparent drop-shadow-[0_2px_14px_rgba(201,168,106,0.28)]">
              {greetingText.title}
            </span>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── COMPANION ROBOT SVG CANVAS ───────────────────────────── */}
      <svg
        viewBox="0 0 500 580"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full relative z-10 overflow-visible"
      >
        <defs>
          {/* OLED Eye Bloom Glow Filter */}
          <filter id="goldGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="4.5" result="blur1" />
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur2" />
            <feMerge>
              <feMergeNode in="blur1" />
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Soft Beacon Glow Filter */}
          <filter id="beaconGlow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Soft Depth Ambient Shadow Filter */}
          <filter id="ambientShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="8" />
            <feOffset dx="0" dy="10" />
            <feComponentTransfer>
              <feFuncA type="linear" slope="0.45" />
            </feComponentTransfer>
            <feMerge>
              <feMergeNode />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Pearl Shell Gradients */}
          <linearGradient id="pearlBodyGrad" x1="180" y1="180" x2="320" y2="480" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="30%" stopColor="#F5F3ED" />
            <stop offset="75%" stopColor="#D8D4CA" />
            <stop offset="100%" stopColor="#A8A398" />
          </linearGradient>

          <linearGradient id="pearlHeadGrad" x1="150" y1="90" x2="350" y2="330" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="35%" stopColor="#F6F4EE" />
            <stop offset="80%" stopColor="#DDD8CD" />
            <stop offset="100%" stopColor="#A9A499" />
          </linearGradient>

          <linearGradient id="darkVisorGrad" x1="250" y1="130" x2="250" y2="290" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#121318" />
            <stop offset="45%" stopColor="#08090C" />
            <stop offset="100%" stopColor="#030405" />
          </linearGradient>

          {/* Champagne & Gold Gradients */}
          <linearGradient id="champagneGold" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FDF2D5" />
            <stop offset="45%" stopColor="#E5C378" />
            <stop offset="100%" stopColor="#A67C2E" />
          </linearGradient>

          <linearGradient id="eyeGoldGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#FFF4D0" />
            <stop offset="40%" stopColor="#FCD16B" />
            <stop offset="100%" stopColor="#E09F20" />
          </linearGradient>

          <radialGradient id="floorLightGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#C9A86A" stopOpacity="0.38" />
            <stop offset="40%" stopColor="#C9A86A" stopOpacity="0.16" />
            <stop offset="85%" stopColor="#C9A86A" stopOpacity="0.02" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </radialGradient>

          {/* Titanium Dark Trim */}
          <linearGradient id="titaniumDark" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#2A2C35" />
            <stop offset="50%" stopColor="#16171D" />
            <stop offset="100%" stopColor="#0D0E12" />
          </linearGradient>
        </defs>

        {/* ── FLOOR PEDESTAL & LIGHT RING ────────────────────────── */}
        <g id="floorPedestal">
          {/* Ambient Floor Glow */}
          <ellipse cx="250" cy="510" rx="170" ry="40" fill="url(#floorLightGrad)" />

          {/* Primary Outer Ring */}
          <ellipse
            cx="250"
            cy="510"
            rx="145"
            ry="28"
            stroke="url(#champagneGold)"
            strokeWidth="1.8"
            opacity="0.8"
            filter="url(#beaconGlow)"
          />
          <ellipse
            cx="250"
            cy="510"
            rx="145"
            ry="28"
            stroke="#FFF4D0"
            strokeWidth="1"
            opacity="0.85"
          />

          {/* Subtle Inner Accent Ring */}
          <ellipse
            cx="250"
            cy="510"
            rx="118"
            ry="21"
            stroke="#C9A86A"
            strokeWidth="0.8"
            strokeDasharray="4 6"
            opacity="0.35"
          />

          {/* Character Contact Shadow */}
          <ellipse cx="250" cy="506" rx="90" ry="18" fill="#000000" opacity="0.8" />
        </g>

        {/* ── ROBOT MASCOT ROOT (FLOATING / BREATHING MOTION) ────── */}
        <motion.g
          id="robotCompanion"
          animate={{
            y: shouldReduceMotion ? 0 : [0, -6, 0],
          }}
          transition={{
            duration: 4.2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        >
          {/* ── LEGS / SITTING LOWER PODS ────────────────────────── */}
          <g id="legsGroup" filter="url(#ambientShadow)">
            {/* Left Leg Pod */}
            <g id="leftLeg">
              <ellipse cx="180" cy="460" rx="42" ry="34" fill="url(#pearlBodyGrad)" />
              {/* Dark Sole Pad */}
              <ellipse cx="174" cy="468" rx="28" ry="18" fill="url(#titaniumDark)" />
            </g>

            {/* Right Leg Pod */}
            <g id="rightLeg">
              <ellipse cx="320" cy="460" rx="42" ry="34" fill="url(#pearlBodyGrad)" />
              {/* Dark Sole Pad */}
              <ellipse cx="326" cy="468" rx="28" ry="18" fill="url(#titaniumDark)" />
            </g>
          </g>

          {/* ── TORSO & BODY (CLEANED REFINED MECHANICAL BODY) ────── */}
          <g id="torsoGroup">
            {/* Main Pear Body Shell */}
            <path
              d="M175 340 C160 410 170 480 250 480 C330 480 340 410 325 340 C310 290 190 290 175 340 Z"
              fill="url(#pearlBodyGrad)"
              filter="url(#ambientShadow)"
            />

            {/* Chest Armor Panel (Titanium Matte) */}
            <path
              d="M198 348 C192 390 200 428 250 428 C300 428 308 390 302 348 C290 328 210 328 198 348 Z"
              fill="url(#titaniumDark)"
            />

            {/* ── ARMS & SLATE TABLET ──────────────────────────── */}
            <g id="tabletAndArms">
              {/* Futuristic Black Glass Slate */}
              <rect
                x="206"
                y="368"
                width="88"
                height="64"
                rx="12"
                fill="#0A0B0F"
                stroke="url(#champagneGold)"
                strokeWidth="1.2"
                filter="url(#ambientShadow)"
              />
              {/* Glowing TARK 4-Point Star on Slate */}
              <motion.path
                d="M250 388 Q250 400 262 400 Q250 400 250 412 Q250 400 238 400 Q250 400 250 388 Z"
                fill="url(#champagneGold)"
                filter="url(#goldGlow)"
                animate={{
                  scale: robotState === 'success' ? [1, 1.25, 1] : [1, 1.08, 1],
                  opacity: robotState === 'passwordFocus' ? 0.4 : [0.8, 1, 0.8],
                }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                style={{ transformOrigin: '250px 400px' }}
              />

              {/* Left Rounded Capsule Arm */}
              <ellipse cx="178" cy="385" rx="18" ry="32" transform="rotate(18 178 385)" fill="url(#pearlBodyGrad)" />
              {/* Left Hand holding slate */}
              <circle cx="204" cy="404" r="13" fill="url(#pearlBodyGrad)" />
              <ellipse cx="206" cy="406" rx="8" ry="4" fill="url(#titaniumDark)" />

              {/* Right Rounded Capsule Arm */}
              <ellipse cx="322" cy="385" rx="18" ry="32" transform="rotate(-18 322 385)" fill="url(#pearlBodyGrad)" />
              {/* Right Hand holding slate */}
              <circle cx="296" cy="404" r="13" fill="url(#pearlBodyGrad)" />
              <ellipse cx="294" cy="406" rx="8" ry="4" fill="url(#titaniumDark)" />
            </g>

            {/* Neck Mechanical Ring */}
            <ellipse cx="250" cy="290" rx="36" ry="12" fill="url(#titaniumDark)" />
          </g>

          {/* ── ROBOT HEAD & HELMET (DYNAMIC CURSOR TRACKING GROUP) ────── */}
          <motion.g
            id="headGroup"
            animate={headTransform}
            transition={{
              type: 'spring',
              stiffness: 180,
              damping: 22,
              mass: 0.75,
            }}
            style={{ transformOrigin: '250px 290px' }}
          >
            {/* ── EAR SENSOR PODS (LEFT & RIGHT) ────────────────── */}
            {/* Left Ear Sensor Pod */}
            <g id="leftEar">
              <ellipse cx="132" cy="200" rx="14" ry="32" fill="url(#pearlHeadGrad)" />
              {/* Glowing Champagne Inner Loop */}
              <ellipse cx="130" cy="200" rx="9" ry="22" fill="url(#titaniumDark)" stroke="url(#champagneGold)" strokeWidth="2" filter="url(#goldGlow)" />
              <circle cx="130" cy="200" r="3.5" fill="#E5C378" />
            </g>

            {/* Right Ear Sensor Pod */}
            <g id="rightEar">
              <ellipse cx="368" cy="200" rx="14" ry="32" fill="url(#pearlHeadGrad)" />
              {/* Glowing Champagne Inner Loop */}
              <ellipse cx="370" cy="200" rx="9" ry="22" fill="url(#titaniumDark)" stroke="url(#champagneGold)" strokeWidth="2" filter="url(#goldGlow)" />
              <circle cx="370" cy="200" r="3.5" fill="#E5C378" />
            </g>

            {/* ── TOP ANTENNA & GLOWING BEACON ──────────────────── */}
            <g id="antennaGroup">
              {/* Metallic Stem */}
              <path
                d="M295 105 Q325 70 338 48"
                stroke="url(#champagneGold)"
                strokeWidth="3"
                strokeLinecap="round"
                fill="none"
              />
              {/* Glowing Beacon Orb */}
              <motion.circle
                cx="338"
                cy="48"
                r="11"
                fill="url(#champagneGold)"
                filter="url(#beaconGlow)"
                animate={{
                  scale: robotState === 'success' ? [1, 1.4, 1.1] : [1, 1.18, 1],
                  opacity: robotState === 'passwordFocus' ? 0.65 : [0.85, 1, 0.85],
                }}
                transition={{
                  duration: robotState === 'success' ? 0.8 : 2.5,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
                style={{ transformOrigin: '338px 48px' }}
              />
              <circle cx="338" cy="48" r="6" fill="#FFF8E0" />
            </g>

            {/* ── MAIN HELMET SHELL ─────────────────────────────── */}
            <rect
              x="136"
              y="92"
              width="228"
              height="195"
              rx="96"
              fill="url(#pearlHeadGrad)"
              filter="url(#ambientShadow)"
            />

            {/* Subtle Helmet Top Rim Light */}
            <path
              d="M175 110 C210 98 290 98 325 110"
              stroke="#FFFFFF"
              strokeWidth="1.5"
              strokeLinecap="round"
              opacity="0.5"
            />

            {/* ── GLOSSY OBSIDIAN VISOR SCREEN ─────────────────── */}
            <g id="visorDisplay">
              {/* Screen Shell */}
              <rect
                x="152"
                y="118"
                width="196"
                height="146"
                rx="68"
                fill="url(#darkVisorGrad)"
                stroke="#1A1C24"
                strokeWidth="1.5"
              />

              {/* Glossy Upper Reflection Curve */}
              <path
                d="M165 140 C195 125 305 125 335 140 C310 162 190 162 165 140 Z"
                fill="#FFFFFF"
                opacity="0.06"
              />

              {/* ── EXPRESSIVE WARM GOLD OLED EYES ─────────────── */}
              <motion.g
                id="eyesContainer"
                animate={gazeOffset}
                transition={{
                  type: 'spring',
                  stiffness: 220,
                  damping: 24,
                }}
              >
                {/* ── LEFT EYE ──────────────────────────────────── */}
                <g id="leftEye">
                  {isEyesClosed ? (
                    /* Closed / Sleeping Privacy Arc `⌒` */
                    <motion.path
                      key="closed-left"
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ duration: 0.2 }}
                      d="M192 196 Q210 183 228 196"
                      stroke="url(#eyeGoldGrad)"
                      strokeWidth="5.5"
                      strokeLinecap="round"
                      fill="none"
                      filter="url(#goldGlow)"
                    />
                  ) : robotState === 'success' ? (
                    /* Joyful Crescent Upward Smile `^` */
                    <motion.path
                      key="success-left"
                      initial={{ scale: 0.8 }}
                      animate={{ scale: 1 }}
                      d="M192 196 Q210 178 228 196"
                      stroke="url(#eyeGoldGrad)"
                      strokeWidth="6"
                      strokeLinecap="round"
                      fill="none"
                      filter="url(#goldGlow)"
                    />
                  ) : (
                    /* Normal Open Glowing Pill / Capsule Eye */
                    <g>
                      {/* Glow Halo */}
                      <rect
                        x="194"
                        y="172"
                        width="32"
                        height="44"
                        rx="16"
                        fill="url(#eyeGoldGrad)"
                        filter="url(#goldGlow)"
                        opacity="0.9"
                      />
                      {/* Crisp Core */}
                      <rect
                        x="196"
                        y="174"
                        width="28"
                        height="40"
                        rx="14"
                        fill="#FFF8E0"
                      />
                      {/* Pupil Highlight */}
                      <circle cx="218" cy="184" r="4.5" fill="#FFFFFF" opacity="0.9" />
                    </g>
                  )}
                </g>

                {/* ── RIGHT EYE ─────────────────────────────────── */}
                <g id="rightEye">
                  {isEyesClosed ? (
                    /* Closed / Sleeping Privacy Arc `⌒` */
                    <motion.path
                      key="closed-right"
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ duration: 0.2 }}
                      d="M272 196 Q290 183 308 196"
                      stroke="url(#eyeGoldGrad)"
                      strokeWidth="5.5"
                      strokeLinecap="round"
                      fill="none"
                      filter="url(#goldGlow)"
                    />
                  ) : robotState === 'success' ? (
                    /* Joyful Crescent Upward Smile `^` */
                    <motion.path
                      key="success-right"
                      initial={{ scale: 0.8 }}
                      animate={{ scale: 1 }}
                      d="M272 196 Q290 178 308 196"
                      stroke="url(#eyeGoldGrad)"
                      strokeWidth="6"
                      strokeLinecap="round"
                      fill="none"
                      filter="url(#goldGlow)"
                    />
                  ) : (
                    /* Normal Open Glowing Pill / Capsule Eye */
                    <g>
                      {/* Glow Halo */}
                      <rect
                        x="274"
                        y="172"
                        width="32"
                        height="44"
                        rx="16"
                        fill="url(#eyeGoldGrad)"
                        filter="url(#goldGlow)"
                        opacity="0.9"
                      />
                      {/* Crisp Core */}
                      <rect
                        x="276"
                        y="174"
                        width="28"
                        height="40"
                        rx="14"
                        fill="#FFF8E0"
                      />
                      {/* Pupil Highlight */}
                      <circle cx="298" cy="184" r="4.5" fill="#FFFFFF" opacity="0.9" />
                    </g>
                  )}
                </g>

                {/* Subtle OLED Cheerful Blush when in Success / Signup */}
                {(robotState === 'success' || robotState === 'signup') && (
                  <g id="cheeks" opacity="0.35">
                    <ellipse cx="186" cy="216" rx="9" ry="4" fill="#E5C378" filter="url(#goldGlow)" />
                    <ellipse cx="314" cy="216" rx="9" ry="4" fill="#E5C378" filter="url(#goldGlow)" />
                  </g>
                )}
              </motion.g>
            </g>
          </motion.g>
        </motion.g>
      </svg>
    </div>
  );
}
