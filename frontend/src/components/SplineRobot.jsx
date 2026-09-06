import React, { useState, useEffect, useCallback, memo, Suspense, lazy } from 'react';

// Lazy load @splinetool/react-spline to ensure zero bundle bloat on other routes
const Spline = lazy(() => import('@splinetool/react-spline'));

const DEFAULT_SPLINE_SCENE = 'https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode';

/**
 * Spline Error Boundary to catch any 3D/WebGL engine or runtime exceptions
 */
class SplineErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.warn('[SplineRobot] Caught Spline runtime error:', error, errorInfo);
    if (this.props.onError) {
      this.props.onError();
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || null;
    }
    return this.props.children;
  }
}

/**
 * SplineRobot - Signature 3D Robot Assistant Companion for TARK AI.
 *
 * Visual & Behavioral Polish:
 * - Positioned on the right side of the hero to provide natural visual balance.
 * - Layered with faint orbital circles and champagne ambient points behind it.
 * - Softened contrast and deeper edge fade so it feels integrated into the dark atmosphere.
 * - Non-blocking pointer events to ensure 100% clickability across the UI.
 */
function SplineRobot({ className = '' }) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [sceneUrl, setSceneUrl] = useState('');

  useEffect(() => {
    const url = import.meta.env.VITE_SPLINE_ROBOT_SCENE_URL || DEFAULT_SPLINE_SCENE;
    if (!url || typeof url !== 'string' || !url.trim()) {
      setHasError(true);
    } else {
      setSceneUrl(url.trim());
    }
  }, []);

  const handleSplineLoad = useCallback(() => {
    setIsLoaded(true);
  }, []);

  const handleSplineError = useCallback((err) => {
    console.warn('[SplineRobot] Failed to load Spline scene:', err);
    setHasError(true);
  }, []);

  if (hasError) {
    return (
      <div
        className="hidden lg:block pointer-events-none select-none opacity-20 transition-opacity duration-1000"
        aria-hidden="true"
        role="presentation"
      >
        <div className="w-[240px] h-[300px] xl:w-[280px] xl:h-[350px] rounded-full bg-gradient-to-br from-amber-500/6 via-amber-500/2 to-transparent blur-3xl" />
      </div>
    );
  }

  return (
    <div
      className={`relative select-none pointer-events-none flex items-center justify-center ${className}`}
      aria-hidden="true"
      role="presentation"
    >
      {/* Background Orbital System behind Robot */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <svg
          viewBox="0 0 300 300"
          className="w-[280px] h-[280px] xl:w-[320px] xl:h-[320px] text-accent/15 animate-orbit-slow"
          fill="none"
        >
          {/* Orbital Circle 1 */}
          <circle
            cx="150"
            cy="150"
            r="125"
            stroke="rgba(201, 168, 106, 0.08)"
            strokeWidth="0.75"
            strokeDasharray="4 8"
          />
          {/* Orbital Circle 2 */}
          <circle
            cx="150"
            cy="150"
            r="95"
            stroke="rgba(201, 168, 106, 0.12)"
            strokeWidth="0.75"
          />
          {/* Sparse Orbital Nodes */}
          <circle cx="245" cy="150" r="1.5" fill="#E1C27A" opacity="0.6" className="animate-subtle-pulse" />
          <circle cx="150" cy="55" r="1.2" fill="#C9A86A" opacity="0.5" />
          <circle cx="83" cy="217" r="1" fill="#8E7548" opacity="0.4" />
        </svg>
      </div>

      {/* Faint Champagne Edge Illumination */}
      <div
        className="absolute inset-0 -m-6 rounded-full pointer-events-none transition-opacity duration-1000"
        style={{
          background: 'radial-gradient(ellipse 60% 60% at 50% 48%, rgba(201,168,106,0.045) 0%, rgba(201,168,106,0.012) 55%, transparent 80%)',
          opacity: isLoaded ? 0.6 : 0.15,
        }}
      />

      {/* Loading Placeholder */}
      {!isLoaded && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-3/4 h-3/4 rounded-full bg-gradient-to-b from-amber-500/4 via-surface2/15 to-transparent blur-2xl animate-pulse" />
        </div>
      )}

      {/* 3D Spline Canvas */}
      <div
        className="w-[216px] h-[270px] sm:w-[243px] sm:h-[306px] lg:w-[279px] lg:h-[351px] xl:w-[315px] xl:h-[396px] 2xl:w-[342px] 2xl:h-[423px] relative transition-opacity duration-700 ease-out overflow-hidden"
        style={{
          opacity: isLoaded ? 1 : 0,
          maskImage: 'radial-gradient(ellipse 65% 65% at 50% 46%, rgba(0,0,0,1) 35%, rgba(0,0,0,0.65) 60%, rgba(0,0,0,0) 88%)',
          WebkitMaskImage: 'radial-gradient(ellipse 65% 65% at 50% 46%, rgba(0,0,0,1) 35%, rgba(0,0,0,0.65) 60%, rgba(0,0,0,0) 88%)',
        }}
      >
        {sceneUrl && (
          <SplineErrorBoundary onError={() => setHasError(true)}>
            <Suspense fallback={null}>
              <div className="w-full h-full pointer-events-none">
                <Spline
                  scene={sceneUrl}
                  onLoad={handleSplineLoad}
                  onError={handleSplineError}
                  style={{ width: '100%', height: '100%', pointerEvents: 'none' }}
                />
              </div>
            </Suspense>
          </SplineErrorBoundary>
        )}
      </div>
    </div>
  );
}

export default memo(SplineRobot);
