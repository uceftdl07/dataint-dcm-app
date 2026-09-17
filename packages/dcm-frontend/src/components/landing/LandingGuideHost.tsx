import React, { useCallback, useEffect, useRef, useState } from 'react';

interface LandingGuideHostProps {
  hovered: boolean;
  clicked: boolean;
}

const BRAND = {
  navy: '#0055A4',
  navyDark: '#0c2340',
  accent: '#00AEEF',
  blouse: '#f8fafc',
  skin: '#e8c4a8',
  skinShadow: '#c9956d',
  hair: '#1e293b',
  hairHighlight: '#334155',
  heel: '#0f172a',
};

/** Elegant profile host — professional guide for the landing access flow. */
export const LandingGuideHost: React.FC<LandingGuideHostProps> = ({ hovered, clicked }) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [blink, setBlink] = useState(false);
  const [pupilOffset, setPupilOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const blinkLoop = () => {
      setBlink(true);
      window.setTimeout(() => setBlink(false), 110);
    };
    const id = window.setInterval(blinkLoop, 3600 + Math.random() * 1800);
    return () => window.clearInterval(id);
  }, []);

  const handleMouseMove = useCallback((event: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const cx = rect.left + rect.width * 0.72;
    const cy = rect.top + rect.height * 0.28;
    const dx = (event.clientX - cx) / rect.width;
    const dy = (event.clientY - cy) / rect.height;
    setPupilOffset({
      x: Math.max(-1, Math.min(1, dx * 2)),
      y: Math.max(-0.6, Math.min(0.6, dy * 1.5)),
    });
  }, []);

  const resetEyes = useCallback(() => setPupilOffset({ x: 0, y: 0 }), []);

  const uid = React.useId().replace(/:/g, '');
  const eyeCx = 152 + pupilOffset.x;
  const eyeCy = 42 + pupilOffset.y;

  return (
    <svg
      ref={svgRef}
      className={`landing-dcm-cat-svg landing-guide-host-svg ${hovered ? 'is-hovered' : ''} ${clicked ? 'is-clicked' : ''} ${blink ? 'is-blinking' : ''}`}
      viewBox="0 0 200 150"
      width="260"
      height="195"
      aria-hidden
      onMouseMove={handleMouseMove}
      onMouseLeave={resetEyes}
    >
      <defs>
        <linearGradient id={`${uid}-blazer`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={BRAND.navy} />
          <stop offset="100%" stopColor={BRAND.navyDark} />
        </linearGradient>
        <linearGradient id={`${uid}-hair`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={BRAND.hairHighlight} />
          <stop offset="100%" stopColor={BRAND.hair} />
        </linearGradient>
        <radialGradient id={`${uid}-ground`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="75%" stopColor="black" stopOpacity="0.28" />
          <stop offset="100%" stopColor="black" stopOpacity="0" />
        </radialGradient>
        <filter id={`${uid}-soft`} x="-15%" y="-10%" width="130%" height="130%">
          <feDropShadow dx="0" dy="2" stdDeviation="2.5" floodColor={BRAND.navyDark} floodOpacity="0.2" />
        </filter>
      </defs>

      <ellipse className="landing-dcm-cat-ground" cx="108" cy="132" rx="42" ry="4" fill={`url(#${uid}-ground)`} />

      {/* Back leg */}
      <g className="landing-dcm-cat-leg-bl" filter={`url(#${uid}-soft)`}>
        <path d="M 82,98 L 78,118 Q 76,126 82,128 L 88,128 Q 94,126 92,118 L 88,98 Z" fill={BRAND.navyDark} />
        <path d="M 80,128 L 86,128 L 88,134 L 82,134 Z" fill={BRAND.heel} />
      </g>

      {/* Hair back / ponytail */}
      <path
        className="landing-dcm-cat-tail-real"
        d="M 118,32 C 108,28 98,34 96,48 C 94,62 100,72 108,78 C 112,68 114,52 118,32 Z"
        fill={`url(#${uid}-hair)`}
      />

      {/* Blazer & skirt silhouette */}
      <g filter={`url(#${uid}-soft)`}>
        <path
          d="M 88,58 C 96,52 118,50 132,58 L 138,78 C 140,92 132,104 118,106 C 100,108 86,100 84,84 Z"
          fill={`url(#${uid}-blazer)`}
        />
        <path
          d="M 86,78 C 100,74 124,74 136,80 L 134,108 C 128,114 104,116 90,112 Z"
          fill={BRAND.navy}
        />
        <path
          d="M 92,62 C 108,58 124,60 130,66 L 128,76 C 118,72 102,72 94,76 Z"
          fill="white"
          fillOpacity="0.12"
        />
        <path
          d="M 100,58 L 104,72 L 108,58"
          stroke={BRAND.accent}
          strokeWidth="1.2"
          fill="none"
          opacity="0.7"
        />
      </g>

      {/* Back arm */}
      <path
        className="landing-dcm-cat-leg-fl"
        d="M 92,62 Q 78,72 74,88 Q 72,94 76,96 Q 80,90 86,78 Z"
        fill={BRAND.navyDark}
      />

      {/* Front leg */}
      <g className="landing-dcm-cat-leg-fr" filter={`url(#${uid}-soft)`}>
        <path d="M 118,98 L 122,118 Q 124,126 118,128 L 112,128 Q 106,126 108,118 L 112,98 Z" fill={`url(#${uid}-blazer)`} />
        <path d="M 114,128 L 120,128 L 122,134 L 116,134 Z" fill={BRAND.heel} />
      </g>

      {/* Welcoming hand */}
      <g className="landing-guide-host-arm">
        <path
          d="M 134,64 Q 148,58 154,48 Q 158,44 156,50 Q 150,60 138,68 Z"
          fill={BRAND.skin}
        />
        <ellipse cx="155" cy="47" rx="4" ry="3.5" fill={BRAND.skin} />
      </g>

      {/* Head */}
      <g className="landing-dcm-cat-head-real" filter={`url(#${uid}-soft)`}>
        <path
          d="M 128,18 C 140,14 158,18 164,32 C 168,42 166,54 158,58 C 150,62 136,58 130,48 C 124,38 122,26 128,18 Z"
          fill={`url(#${uid}-hair)`}
        />
        <ellipse cx="148" cy="44" rx="16" ry="18" fill={BRAND.skin} />
        <path
          d="M 132,36 C 138,30 152,30 160,38 C 154,34 142,34 136,38 Z"
          fill={BRAND.hair}
        />
        <path
          d="M 160,38 C 166,44 168,52 164,58 C 162,50 162,44 160,38 Z"
          fill={BRAND.skinShadow}
          fillOpacity="0.25"
        />

        <g className="landing-dcm-cat-eye">
          <ellipse cx={eyeCx} cy={eyeCy} rx="3.2" ry="2.4" fill={BRAND.navyDark} />
          <circle cx={eyeCx + 0.8} cy={eyeCy - 0.6} r="0.7" fill="white" fillOpacity="0.85" />
          <path
            className="landing-dcm-cat-lid-real"
            d={`M ${eyeCx - 4} ${eyeCy - 2} Q ${eyeCx} ${eyeCy - 3.5} ${eyeCx + 4} ${eyeCy - 2} Q ${eyeCx} ${eyeCy + 1} ${eyeCx - 4} ${eyeCy - 2}`}
            fill={BRAND.skin}
          />
        </g>

        <path
          d="M 162,50 Q 166,52 168,50"
          stroke={BRAND.skinShadow}
          strokeWidth="1"
          fill="none"
          strokeLinecap="round"
          opacity="0.6"
        />
        <ellipse cx="165" cy="48" rx="1.2" ry="1" fill={BRAND.skinShadow} fillOpacity="0.35" />
      </g>
    </svg>
  );
};
