import React, { useEffect, useRef } from 'react';

/**
 * TarkAmbientBackground - Premium ambient hero background for TARK AI.
 * 
 * Visual Concept: "Intelligence in Motion"
 * - Dark charcoal/black environment with a restrained champagne-gold particle field.
 * - Smooth flow-field motion with intelligent node clustering, subtle data streaks,
 *   abstract Tark "T" constellation dissolutions, and capability structures.
 * - "Quiet center / active edges" composition ensuring 100% hero & composer legibility.
 * - Ultra-lightweight Canvas 2D engine with adaptive particle count, visibility pausing,
 *   and prefers-reduced-motion support.
 */
export default function TarkAmbientBackground({ mode = 'normal', className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let animationFrameId;
    let width = 0;
    let height = 0;
    let dpr = 1;
    let isVisible = true;
    let prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Pointer state with smooth damping
    const mouse = {
      x: -1000,
      y: -1000,
      targetX: -1000,
      targetY: -1000,
      isHovering: false,
      radius: 140,
    };

    // Color palette constants (Champagne gold & deep dark accents)
    const COLORS = {
      goldPrimary: 'rgba(201, 168, 106,',     // #C9A86A
      goldWarm: 'rgba(225, 194, 122,',        // #E1C27A
      goldMuted: 'rgba(184, 155, 98,',        // #B89B62
      goldDeep: 'rgba(142, 117, 72,',         // #8E7548
      goldFaint: 'rgba(201, 168, 106, 0.035)',
    };

    // Fast pseudo-Perlin 2D simplex/noise approximation for organic fluid flow
    function getNoise(x, y, t) {
      const s = 0.0018;
      const n1 = Math.sin(x * s + t * 0.25) * Math.cos(y * s + t * 0.2);
      const n2 = Math.sin((x + y) * (s * 0.7) - t * 0.15) * 0.5;
      const n3 = Math.cos(x * s * 1.5 - y * s * 1.2 + t * 0.3) * 0.25;
      return (n1 + n2 + n3) * Math.PI * 2;
    }

    // Particle pool
    let particles = [];
    let dataStreaks = [];
    let abstractTNodes = [];

    // Setup TARK "T" abstract constellation anchors
    function initTConstellation(w, h) {
      abstractTNodes = [];
      // Subtle position: top-right or mid-left area, faint and non-intrusive
      const centerX = w * 0.82;
      const centerY = h * 0.32;
      const scale = Math.min(w, h) * 0.09;

      // Horizontal crossbar points
      for (let i = -4; i <= 4; i++) {
        abstractTNodes.push({
          relX: centerX + (i * scale * 0.22),
          relY: centerY - scale * 0.45,
          targetAlpha: 0.22,
        });
      }
      // Vertical stem points
      for (let j = -2; j <= 5; j++) {
        abstractTNodes.push({
          relX: centerX,
          relY: centerY + (j * scale * 0.18),
          targetAlpha: 0.18,
        });
      }
    }

    // Initialize particles based on screen size
    function initParticles() {
      const isMobile = width < 640;
      const isTablet = width >= 640 && width < 1024;
      
      // Restrained, premium adaptive particle density
      let count = isMobile ? 22 : isTablet ? 42 : 68;
      if (mode === 'reasoning') count = Math.round(count * 1.15);
      if (mode === 'fast') count = Math.round(count * 0.75);

      particles = [];
      for (let i = 0; i < count; i++) {
        const isNode = i % 8 === 0;
        const isStructure = i % 20 === 0;
        const colorVariation = i % 4;
        let colorPrefix = COLORS.goldPrimary;
        if (colorVariation === 1) colorPrefix = COLORS.goldWarm;
        else if (colorVariation === 2) colorPrefix = COLORS.goldMuted;
        else if (colorVariation === 3) colorPrefix = COLORS.goldDeep;

        // Bias initial positions towards perimeter & bottom
        let x, y;
        if (Math.random() < 0.8) {
          // Edges & bottom
          if (Math.random() < 0.5) {
            x = Math.random() < 0.5 ? Math.random() * (width * 0.28) : width * 0.72 + Math.random() * (width * 0.28);
            y = Math.random() * height;
          } else {
            x = Math.random() * width;
            y = height * 0.7 + Math.random() * (height * 0.3);
          }
        } else {
          x = Math.random() * width;
          y = Math.random() * height;
        }

        particles.push({
          x,
          y,
          vx: (Math.random() - 0.5) * 0.18,
          vy: (Math.random() - 0.5) * 0.18,
          baseSize: isNode ? 1.2 + Math.random() * 0.8 : 0.6 + Math.random() * 0.7,
          size: 0.8,
          alpha: Math.random() * 0.18 + 0.05,
          baseAlpha: isNode ? 0.22 + Math.random() * 0.14 : 0.09 + Math.random() * 0.12,
          colorPrefix,
          isNode,
          isStructure,
          structType: i % 3,
          pulsePhase: Math.random() * Math.PI * 2,
          life: Math.random() * 1000,
          maxLife: 900 + Math.random() * 1400,
          tNodeIndex: i < abstractTNodes.length ? i : -1,
        });
      }

      // Initialize subtle data streaks (rare, smooth pulses across flow lines)
      dataStreaks = [
        { x: width * 0.08, y: height * 0.22, length: 90, speed: 0.5, angle: 0.65, alpha: 0, life: 0, maxLife: 360, delay: 60 },
        { x: width * 0.88, y: height * 0.38, length: 120, speed: 0.4, angle: 0.78, alpha: 0, life: 0, maxLife: 450, delay: 240 },
      ];
    }

    // Resize Handler
    function handleResize() {
      if (!canvas) return;
      const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : { width: window.innerWidth, height: window.innerHeight };
      width = Math.max(rect.width, 300);
      height = Math.max(rect.height, 300);
      dpr = Math.min(window.devicePixelRatio || 1, 2);

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);

      initTConstellation(width, height);
      initParticles();
    }

    handleResize();
    window.addEventListener('resize', handleResize);

    // Mouse movement interaction (gentle vector field influence, disabled on mobile)
    function handlePointerMove(e) {
      if (width < 640) return;
      const rect = canvas.getBoundingClientRect();
      mouse.targetX = e.clientX - rect.left;
      mouse.targetY = e.clientY - rect.top;
      mouse.isHovering = true;
    }

    function handlePointerLeave() {
      mouse.isHovering = false;
      mouse.targetX = -1000;
      mouse.targetY = -1000;
    }

    const parentEl = canvas.parentElement || window;
    parentEl.addEventListener('pointermove', handlePointerMove, { passive: true });
    parentEl.addEventListener('pointerleave', handlePointerLeave, { passive: true });

    // Document visibility change listener (pauses RAF loop when tab is hidden)
    function handleVisibilityChange() {
      isVisible = !document.hidden;
      if (isVisible && !animationFrameId) {
        lastTime = performance.now();
        animationFrameId = requestAnimationFrame(render);
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Reduced motion listener
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handleMotionChange = (e) => {
      prefersReducedMotion = e.matches;
    };
    motionQuery.addEventListener('change', handleMotionChange);

    let lastTime = performance.now();
    let globalTime = 0;

    // Render loop
    function render(currentTime) {
      if (!isVisible) {
        animationFrameId = null;
        return;
      }

      const dt = Math.min((currentTime - lastTime) / 1000, 0.1);
      lastTime = currentTime;
      globalTime += dt * (prefersReducedMotion ? 0.04 : 0.65);

      // Smooth mouse interpolation
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;

      ctx.clearRect(0, 0, width, height);

      // ==========================================
      // LAYER 1 & 2: BASE ILLUMINATION & ROBOT HALO
      // ==========================================
      
      // Top-center very gentle hero radial glow
      const heroGlow = ctx.createRadialGradient(
        width * 0.5, height * 0.36, 10,
        width * 0.5, height * 0.36, Math.max(width * 0.5, 360)
      );
      heroGlow.addColorStop(0, 'rgba(201, 168, 106, 0.016)');
      heroGlow.addColorStop(0.5, 'rgba(201, 168, 106, 0.004)');
      heroGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = heroGlow;
      ctx.fillRect(0, 0, width, height);

      // Dedicated subtle warm ambient halo supporting the right-side robot companion zone
      if (width >= 1024) {
        const robotZoneGlow = ctx.createRadialGradient(
          width * 0.84, height * 0.34, 10,
          width * 0.84, height * 0.34, Math.min(width * 0.28, 280)
        );
        robotZoneGlow.addColorStop(0, 'rgba(201, 168, 106, 0.028)');
        robotZoneGlow.addColorStop(0.55, 'rgba(201, 168, 106, 0.008)');
        robotZoneGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = robotZoneGlow;
        ctx.fillRect(0, 0, width, height);
      }

      // Bottom ambient horizon illumination (Knowledge Base & Compute depth)
      const bottomHorizon = ctx.createLinearGradient(0, height * 0.75, 0, height);
      bottomHorizon.addColorStop(0, 'rgba(0, 0, 0, 0)');
      bottomHorizon.addColorStop(0.7, 'rgba(201, 168, 106, 0.008)');
      bottomHorizon.addColorStop(1, 'rgba(201, 168, 106, 0.022)');
      ctx.fillStyle = bottomHorizon;
      ctx.fillRect(0, height * 0.75, width, height * 0.25);

      // Bottom subtle perspective grid lines (ultra faint architectural depth)
      const gridHorizonY = height * 0.9;
      const gridVanishX = width * 0.5;
      
      ctx.beginPath();
      ctx.lineWidth = 0.5;
      ctx.strokeStyle = 'rgba(201, 168, 106, 0.012)';

      // Subtle perspective rays originating from vanishing point towards bottom
      const rayCount = 6;
      for (let r = 0; r <= rayCount; r++) {
        const bottomX = (width / rayCount) * r;
        ctx.moveTo(gridVanishX + (bottomX - gridVanishX) * 0.45, gridHorizonY);
        ctx.lineTo(bottomX, height);
      }
      ctx.stroke();

      // ==========================================
      // LAYER 3 & 4: PARTICLES, FLOW FIELD & CONNECTIONS
      // ==========================================

      // T-constellation cycle (every 30s)
      const tCyclePeriod = 30;
      const tCycleTime = globalTime % tCyclePeriod;
      let tInfluenceWeight = 0;
      if (tCycleTime > 10 && tCycleTime < 15) {
        const progress = (tCycleTime - 10) / 2;
        tInfluenceWeight = Math.min(progress, 1);
      } else if (tCycleTime >= 15 && tCycleTime < 19) {
        const progress = 1 - (tCycleTime - 15) / 4;
        tInfluenceWeight = Math.max(progress, 0);
      }

      const centerHeroX = width * 0.5;
      const centerHeroY = height * 0.42;
      const heroZoneRadiusX = width * 0.42;
      const heroZoneRadiusY = height * 0.36;

      // Update particle positions & properties
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.life += dt * 60;
        p.pulsePhase += dt * 1.2;

        // Calculate flow field angle (slow, organic motion)
        const flowAngle = getNoise(p.x, p.y, globalTime);
        const flowSpeed = (prefersReducedMotion ? 0.05 : 0.22) * (mode === 'reasoning' ? 1.15 : mode === 'fast' ? 0.8 : 1);
        
        let targetVx = Math.cos(flowAngle) * flowSpeed;
        let targetVy = Math.sin(flowAngle) * flowSpeed * 0.6;

        // Mode specific vector modifications
        if (mode === 'deep_research') {
          targetVy -= 0.1;
        } else if (mode === 'coding') {
          if (Math.abs(targetVx) > Math.abs(targetVy)) targetVy *= 0.3;
          else targetVx *= 0.3;
        }

        // T-Constellation guide force
        if (p.tNodeIndex >= 0 && p.tNodeIndex < abstractTNodes.length && tInfluenceWeight > 0.01) {
          const tTarget = abstractTNodes[p.tNodeIndex];
          const dx = tTarget.relX - p.x;
          const dy = tTarget.relY - p.y;
          targetVx += dx * 0.012 * tInfluenceWeight;
          targetVy += dy * 0.012 * tInfluenceWeight;
        }

        // Strong Quiet Center Repulsion (leaves center workspace calm & legible)
        const dxCenter = p.x - centerHeroX;
        const dyCenter = p.y - centerHeroY;
        const normDistX = dxCenter / heroZoneRadiusX;
        const normDistY = dyCenter / heroZoneRadiusY;
        const centerDistSq = normDistX * normDistX + normDistY * normDistY;

        if (centerDistSq < 1.0) {
          const repelStrength = (1.0 - Math.sqrt(centerDistSq)) * 0.5;
          targetVx += (dxCenter / (Math.abs(dxCenter) + 1)) * repelStrength;
          targetVy += (dyCenter / (Math.abs(dyCenter) + 1)) * repelStrength;
        }

        // Interactive mouse deflection
        if (mouse.isHovering) {
          const dxMouse = p.x - mouse.x;
          const dyMouse = p.y - mouse.y;
          const distMouse = Math.sqrt(dxMouse * dxMouse + dyMouse * dyMouse);
          if (distMouse < mouse.radius && distMouse > 1) {
            const force = (1 - distMouse / mouse.radius) * 0.45;
            targetVx += (dxMouse / distMouse) * force;
            targetVy += (dyMouse / distMouse) * force;
          }
        }

        // Apply velocity with smooth easing
        p.vx += (targetVx - p.vx) * 0.04;
        p.vy += (targetVy - p.vy) * 0.04;

        p.x += p.vx;
        p.y += p.vy;

        // Wrap edges gracefully
        const margin = 30;
        if (p.x < -margin) p.x = width + margin;
        if (p.x > width + margin) p.x = -margin;
        if (p.y < -margin) p.y = height + margin;
        if (p.y > height + margin) p.y = -margin;

        // Calculate dynamic alpha with Quiet Center suppression
        let centerFade = 1;
        if (centerDistSq < 1.0) {
          centerFade = Math.max(0.05, centerDistSq * 0.4);
        }

        const pulse = (Math.sin(p.pulsePhase) + 1) * 0.5;
        p.alpha = p.baseAlpha * (0.75 + pulse * 0.25) * centerFade;
        p.size = p.baseSize * (0.9 + pulse * 0.2);
      }

      // Draw subtle connection lines between nearby particles
      const maxConnectDist = mode === 'reasoning' ? 75 : 62;
      const maxConnectDistSq = maxConnectDist * maxConnectDist;
      
      ctx.lineWidth = 0.5;
      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        if (p1.alpha < 0.04) continue;

        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          if (p2.alpha < 0.04) continue;

          const dx = p1.x - p2.x;
          const dy = p1.y - p2.y;
          const distSq = dx * dx + dy * dy;

          if (distSq < maxConnectDistSq) {
            const dist = Math.sqrt(distSq);
            const lineAlpha = (1 - dist / maxConnectDist) * Math.min(p1.alpha, p2.alpha) * 0.35;
            if (lineAlpha > 0.008) {
              ctx.strokeStyle = `rgba(212, 175, 55, ${lineAlpha})`;
              ctx.beginPath();
              ctx.moveTo(p1.x, p1.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.stroke();
            }
          }
        }
      }

      // Draw particles & abstract capability structures
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        if (p.alpha <= 0.008) continue;

        // Particle core
        ctx.fillStyle = `${p.colorPrefix} ${p.alpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();

        // Subtle node halo for connector hubs
        if (p.isNode && p.alpha > 0.12) {
          ctx.fillStyle = `${p.colorPrefix} ${p.alpha * 0.12})`;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.size * 2.4, 0, Math.PI * 2);
          ctx.fill();
        }

        // Abstract subtle capability structures (brackets, doc rects, forks)
        if (p.isStructure && p.alpha > 0.1 && !prefersReducedMotion) {
          ctx.strokeStyle = `${p.colorPrefix} ${p.alpha * 0.25})`;
          ctx.lineWidth = 0.5;
          const s = 4.5;

          if (mode === 'coding' || p.structType === 0) {
            ctx.beginPath();
            ctx.moveTo(p.x + s * 0.6, p.y - s);
            ctx.lineTo(p.x - s * 0.4, p.y - s);
            ctx.lineTo(p.x - s * 0.4, p.y + s);
            ctx.lineTo(p.x + s * 0.6, p.y + s);
            ctx.stroke();
          } else if (mode === 'rag' || p.structType === 1) {
            ctx.beginPath();
            ctx.strokeRect(p.x - s * 0.5, p.y - s * 0.7, s * 1.0, s * 1.4);
          } else if (p.structType === 2) {
            ctx.beginPath();
            ctx.moveTo(p.x - s, p.y);
            ctx.lineTo(p.x, p.y);
            ctx.lineTo(p.x + s * 0.7, p.y - s * 0.5);
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p.x + s * 0.7, p.y + s * 0.5);
            ctx.stroke();
          }
        }
      }

      // ==========================================
      // LAYER 5: OCCASIONAL DATA STREAKS
      // ==========================================
      if (!prefersReducedMotion) {
        for (let s = 0; s < dataStreaks.length; s++) {
          const streak = dataStreaks[s];
          streak.life += dt * 60;
          if (streak.life > streak.maxLife + streak.delay) {
            // Reset streak with new position
            streak.life = 0;
            streak.x = Math.random() < 0.5 ? Math.random() * width * 0.3 : width * 0.7 + Math.random() * width * 0.3;
            streak.y = Math.random() * height;
            streak.angle = 0.45 + Math.random() * 0.4;
            streak.length = 80 + Math.random() * 120;
            streak.speed = 0.7 + Math.random() * 0.6;
          }

          if (streak.life > streak.delay) {
            const activeLife = streak.life - streak.delay;
            const progress = activeLife / streak.maxLife; // 0 to 1
            const streakAlpha = Math.sin(progress * Math.PI) * 0.18; // smooth in & out

            streak.x += Math.cos(streak.angle) * streak.speed;
            streak.y += Math.sin(streak.angle) * streak.speed * 0.6;

            if (streakAlpha > 0.01) {
              const tailX = streak.x - Math.cos(streak.angle) * streak.length;
              const tailY = streak.y - Math.sin(streak.angle) * streak.length * 0.6;

              const streakGradient = ctx.createLinearGradient(tailX, tailY, streak.x, streak.y);
              streakGradient.addColorStop(0, 'rgba(212, 175, 55, 0)');
              streakGradient.addColorStop(0.7, `rgba(229, 212, 179, ${streakAlpha * 0.4})`);
              streakGradient.addColorStop(1, `rgba(212, 175, 55, ${streakAlpha})`);

              ctx.strokeStyle = streakGradient;
              ctx.lineWidth = 0.75;
              ctx.beginPath();
              ctx.moveTo(tailX, tailY);
              ctx.lineTo(streak.x, streak.y);
              ctx.stroke();

              // Micro head point
              ctx.fillStyle = `rgba(255, 245, 215, ${streakAlpha * 1.3})`;
              ctx.beginPath();
              ctx.arc(streak.x, streak.y, 0.9, 0, Math.PI * 2);
              ctx.fill();
            }
          }
        }
      }

      // ==========================================
      // LAYER 6: PERIMETER VIGNETTE OVERLAY
      // ==========================================
      // Soft outer vignette framing the AI workspace
      const vignette = ctx.createRadialGradient(
        width * 0.5, height * 0.5, Math.min(width, height) * 0.35,
        width * 0.5, height * 0.5, Math.max(width, height) * 0.85
      );
      vignette.addColorStop(0, 'rgba(0, 0, 0, 0)');
      vignette.addColorStop(0.65, 'rgba(0, 0, 0, 0.45)');
      vignette.addColorStop(1, 'rgba(0, 0, 0, 0.95)');
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, width, height);

      animationFrameId = requestAnimationFrame(render);
    }

    animationFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      parentEl.removeEventListener('pointermove', handlePointerMove);
      parentEl.removeEventListener('pointerleave', handlePointerLeave);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      motionQuery.removeEventListener('change', handleMotionChange);
    };
  }, [mode]);

  return (
    <div
      className={`absolute inset-0 pointer-events-none overflow-hidden z-0 select-none ${className}`}
      aria-hidden="true"
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full block opacity-100 transition-opacity duration-700"
      />
    </div>
  );
}
