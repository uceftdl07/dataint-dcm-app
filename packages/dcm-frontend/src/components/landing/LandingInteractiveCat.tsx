import React, { useCallback, useEffect, useRef, useState } from 'react';

interface LandingInteractiveCatProps {
  hovered: boolean;
  clicked: boolean;
}

export const LandingInteractiveCat: React.FC<LandingInteractiveCatProps> = ({ hovered, clicked }) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [blink, setBlink] = useState(false);
  const [pupilOffset, setPupilOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const blinkLoop = () => {
      setBlink(true);
      window.setTimeout(() => setBlink(false), 140);
    };
    const id = window.setInterval(blinkLoop, 3200 + Math.random() * 2000);
    return () => window.clearInterval(id);
  }, []);

  const handleMouseMove = useCallback((event: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const cx = rect.left + rect.width * 0.5;
    const cy = rect.top + rect.height * 0.38;
    const dx = (event.clientX - cx) / rect.width;
    const dy = (event.clientY - cy) / rect.height;
    setPupilOffset({
      x: Math.max(-2.5, Math.min(2.5, dx * 5)),
      y: Math.max(-1.5, Math.min(1.5, dy * 4)),
    });
  }, []);

  const resetEyes = useCallback(() => setPupilOffset({ x: 0, y: 0 }), []);

  return (
    <svg
      ref={svgRef}
      className={`landing-cat-svg ${hovered ? 'is-hovered' : ''} ${clicked ? 'is-clicked' : ''} ${blink ? 'is-blinking' : ''}`}
      viewBox="0 0 120 140"
      width="110"
      height="128"
      aria-hidden
      onMouseMove={handleMouseMove}
      onMouseLeave={resetEyes}
    >
      <defs>
        <linearGradient id="cat-body-grad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#67e8f9" />
          <stop offset="45%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#0055A4" />
        </linearGradient>
        <linearGradient id="cat-body-shadow" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0c2340" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#0055A4" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="cat-ear-grad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#a5f3fc" />
          <stop offset="100%" stopColor="#0055A4" />
        </linearGradient>
        <radialGradient id="cat-cheek-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </radialGradient>
        <filter id="cat-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="cat-soft-shadow" x="-20%" y="-10%" width="140%" height="140%">
          <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#0055A4" floodOpacity="0.28" />
        </filter>
      </defs>

      {/* Ground glow */}
      <ellipse className="landing-cat-ground-glow" cx="60" cy="132" rx="34" ry="5" fill="url(#cat-cheek-glow)" />

      {/* Tail */}
      <g className="landing-cat-tail-group" filter="url(#cat-soft-shadow)">
        <path
          d="M88 78 C102 62, 108 48, 100 32 C96 24, 88 28, 90 38 C92 50, 86 64, 82 74 Z"
          fill="url(#cat-body-grad)"
          stroke="white"
          strokeWidth="2"
        />
      </g>

      {/* Back paws */}
      <g className="landing-cat-paw landing-cat-paw-back-left" filter="url(#cat-soft-shadow)">
        <ellipse cx="38" cy="118" rx="7" ry="9" fill="url(#cat-body-grad)" stroke="white" strokeWidth="1.5" />
        <ellipse cx="38" cy="124" rx="8" ry="3" fill="#0c2340" opacity="0.15" />
      </g>
      <g className="landing-cat-paw landing-cat-paw-back-right" filter="url(#cat-soft-shadow)">
        <ellipse cx="58" cy="118" rx="7" ry="9" fill="url(#cat-body-grad)" stroke="white" strokeWidth="1.5" />
        <ellipse cx="58" cy="124" rx="8" ry="3" fill="#0c2340" opacity="0.15" />
      </g>

      {/* Body */}
      <g filter="url(#cat-soft-shadow)">
        <ellipse cx="60" cy="88" rx="34" ry="30" fill="url(#cat-body-grad)" stroke="white" strokeWidth="2.5" />
        <ellipse cx="60" cy="92" rx="28" ry="22" fill="url(#cat-body-shadow)" />
        {/* Tech chest badge */}
        <circle cx="60" cy="86" r="10" fill="white" fillOpacity="0.2" />
        <path
          d="M56 86 L60 82 L64 86 L60 90 Z"
          fill="#22d3ee"
          className="landing-cat-badge-pulse"
        />
      </g>

      {/* Front paws */}
      <g className="landing-cat-paw landing-cat-paw-front-left" filter="url(#cat-soft-shadow)">
        <ellipse cx="44" cy="112" rx="7.5" ry="10" fill="url(#cat-body-grad)" stroke="white" strokeWidth="1.5" />
      </g>
      <g className="landing-cat-paw landing-cat-paw-front-right" filter="url(#cat-soft-shadow)">
        <ellipse cx="76" cy="112" rx="7.5" ry="10" fill="url(#cat-body-grad)" stroke="white" strokeWidth="1.5" />
      </g>

      {/* Head group */}
      <g className="landing-cat-head-group" filter="url(#cat-glow)">
        {/* Ears */}
        <path
          className="landing-cat-ear landing-cat-ear-left"
          d="M34 42 L42 18 L50 40 Z"
          fill="url(#cat-ear-grad)"
          stroke="white"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <path d="M38 38 L42 24 L46 38 Z" fill="#22d3ee" fillOpacity="0.45" />
        <path
          className="landing-cat-ear landing-cat-ear-right"
          d="M70 40 L78 18 L86 42 Z"
          fill="url(#cat-ear-grad)"
          stroke="white"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <path d="M74 38 L78 24 L82 38 Z" fill="#22d3ee" fillOpacity="0.45" />

        {/* Face */}
        <circle cx="60" cy="48" r="28" fill="url(#cat-body-grad)" stroke="white" strokeWidth="2.5" />
        <ellipse cx="48" cy="54" rx="8" ry="5" fill="url(#cat-cheek-glow)" />
        <ellipse cx="72" cy="54" rx="8" ry="5" fill="url(#cat-cheek-glow)" />

        {/* Eyes */}
        <g className="landing-cat-eyes">
          <ellipse className="landing-cat-eye-white" cx="48" cy="46" rx="9" ry="10" fill="white" />
          <ellipse className="landing-cat-eye-white" cx="72" cy="46" rx="9" ry="10" fill="white" />
          <ellipse
            className="landing-cat-pupil"
            cx={48 + pupilOffset.x}
            cy={46 + pupilOffset.y}
            rx="4.5"
            ry="5.5"
            fill="#0c2340"
          />
          <ellipse
            className="landing-cat-pupil"
            cx={72 + pupilOffset.x}
            cy={46 + pupilOffset.y}
            rx="4.5"
            ry="5.5"
            fill="#0c2340"
          />
          <circle cx={50 + pupilOffset.x} cy={44 + pupilOffset.y} r="2" fill="#22d3ee" className="landing-cat-eye-shine" />
          <circle cx={74 + pupilOffset.x} cy={44 + pupilOffset.y} r="2" fill="#22d3ee" className="landing-cat-eye-shine" />
          {/* Blink lids */}
          <ellipse className="landing-cat-lid" cx="48" cy="46" rx="9" ry="10" fill="url(#cat-body-grad)" />
          <ellipse className="landing-cat-lid" cx="72" cy="46" rx="9" ry="10" fill="url(#cat-body-grad)" />
        </g>

        {/* Nose & mouth */}
        <path d="M60 54 L56 58 L64 58 Z" fill="#22d3ee" />
        <path
          d="M60 58 Q56 62 52 60 M60 58 Q64 62 68 60"
          fill="none"
          stroke="white"
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0.85"
        />

        {/* Whiskers */}
        <g className="landing-cat-whiskers" stroke="white" strokeWidth="1.2" strokeLinecap="round" opacity="0.75">
          <line x1="30" y1="50" x2="44" y2="52" />
          <line x1="28" y1="56" x2="44" y2="56" />
          <line x1="30" y1="62" x2="44" y2="60" />
          <line x1="90" y1="52" x2="76" y2="52" />
          <line x1="92" y1="56" x2="76" y2="56" />
          <line x1="90" y1="62" x2="76" y2="60" />
        </g>
      </g>

      {/* Sparkles on hover */}
      <g className="landing-cat-sparkles">
        <circle cx="22" cy="30" r="2" fill="#67e8f9" />
        <circle cx="98" cy="28" r="1.5" fill="#22d3ee" />
        <circle cx="104" cy="50" r="2" fill="#a5f3fc" />
      </g>
    </svg>
  );
};
