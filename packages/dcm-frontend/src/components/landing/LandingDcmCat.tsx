import React, { useCallback, useEffect, useRef, useState } from 'react';

interface LandingDcmCatProps {
  hovered: boolean;
  clicked: boolean;
}

/** Azur palette — realistic profile walking cat (from Félin Bleu generator). */
const AZUR = {
  coat: '#2563eb',
  coatDark: '#1e3a8a',
  eye: '#fbbf24',
  ear: '#fecdd3',
};

/** DCM-Cat — realistic blue profile mascot with walk / wag / bob animations. */
export const LandingDcmCat: React.FC<LandingDcmCatProps> = ({ hovered, clicked }) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [blink, setBlink] = useState(false);
  const [pupilOffset, setPupilOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const blinkLoop = () => {
      setBlink(true);
      window.setTimeout(() => setBlink(false), 120);
    };
    const id = window.setInterval(blinkLoop, 3200 + Math.random() * 2000);
    return () => window.clearInterval(id);
  }, []);

  const handleMouseMove = useCallback((event: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const cx = rect.left + rect.width * 0.78;
    const cy = rect.top + rect.height * 0.32;
    const dx = (event.clientX - cx) / rect.width;
    const dy = (event.clientY - cy) / rect.height;
    setPupilOffset({
      x: Math.max(-1.2, Math.min(1.2, dx * 2.5)),
      y: Math.max(-0.8, Math.min(0.8, dy * 2)),
    });
  }, []);

  const resetEyes = useCallback(() => setPupilOffset({ x: 0, y: 0 }), []);

  const uid = React.useId().replace(/:/g, '');
  const c = AZUR;
  const eyeCx = 158 + pupilOffset.x;
  const eyeCy = 48 + pupilOffset.y;

  return (
    <svg
      ref={svgRef}
      className={`landing-dcm-cat-svg ${hovered ? 'is-hovered' : ''} ${clicked ? 'is-clicked' : ''} ${blink ? 'is-blinking' : ''}`}
      viewBox="0 0 200 150"
      width="182"
      height="137"
      aria-hidden
      onMouseMove={handleMouseMove}
      onMouseLeave={resetEyes}
    >
      <defs>
        <linearGradient id={`${uid}-coat`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c.coat} />
          <stop offset="100%" stopColor={c.coatDark} />
        </linearGradient>
        <radialGradient id={`${uid}-shadow`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="80%" stopColor="black" stopOpacity="0.35" />
          <stop offset="100%" stopColor="black" stopOpacity="0" />
        </radialGradient>
      </defs>

      <ellipse className="landing-dcm-cat-ground" cx="110" cy="130" rx="46" ry="4.5" fill={`url(#${uid}-shadow)`} />

      {/* Back legs (depth) */}
      <path
        id="leg_fl"
        className="landing-dcm-cat-leg-fl"
        d="M 118,95 Q 112,118 106,128 Q 103,130 105,128 Q 111,118 118,95"
        fill={c.coatDark}
      />
      <path
        id="leg_bl"
        className="landing-dcm-cat-leg-bl"
        d="M 78,90 Q 84,118 90,128 Q 93,130 91,128 Q 85,118 78,90"
        fill={c.coatDark}
      />

      {/* Tail */}
      <path
        id="tail"
        className="landing-dcm-cat-tail-real"
        d="M 70,75 C 45,70 35,50 40,35 C 43,25 55,20 60,25 C 60,35 55,45 65,60 C 70,68 70,75 70,75 Z"
        fill={`url(#${uid}-coat)`}
      />

      {/* Body */}
      <path
        d="M 70,75 C 80,62 125,60 145,72 C 152,80 148,98 128,100 C 95,102 80,100 70,88 Z"
        fill={`url(#${uid}-coat)`}
      />
      <path
        d="M 85,65 C 100,60 120,60 135,66 C 120,63 100,63 85,65 Z"
        fill="white"
        fillOpacity="0.18"
      />
      <path
        d="M 90,70 C 110,67 130,70 140,77 C 130,87 110,92 90,90 Z"
        fill="black"
        fillOpacity="0.12"
      />

      {/* Head */}
      <g id="head" className="landing-dcm-cat-head-real">
        <path d="M 133,40 145,20 152,43 Z" fill={c.coatDark} />
        <path d="M 136,39 143,26 148,40 Z" fill={c.ear} />
        <path d="M 152,43 165,22 168,46 Z" fill={`url(#${uid}-coat)`} />
        <path d="M 156,41 162,28 164,43 Z" fill={c.ear} />
        <circle cx="155" cy="55" r="22" fill={`url(#${uid}-coat)`} />
        <path
          d="M 145,45 C 152,40 168,42 172,52 C 165,58 148,55 145,45 Z"
          fill="white"
          fillOpacity="0.08"
        />

        <g className="landing-dcm-cat-eye">
          <ellipse className="landing-dcm-cat-iris" cx={eyeCx} cy={eyeCy} rx="4.5" ry="4.5" fill={c.eye} />
          <ellipse className="landing-dcm-cat-pupil-slot" cx={eyeCx} cy={eyeCy} rx="1.5" ry="3.5" fill="#0f172a" />
          <circle className="landing-dcm-cat-shine-main" cx={eyeCx + 1.5} cy={eyeCy - 2} r="1.2" fill="white" fillOpacity="0.8" />
          <circle className="landing-dcm-cat-shine-sub" cx={eyeCx - 1.5} cy={eyeCy + 2} r="0.6" fill="white" fillOpacity="0.4" />
          <ellipse className="landing-dcm-cat-lid-real" cx={eyeCx} cy={eyeCy} rx="5" ry="5" fill={c.coat} />
        </g>

        <polygon points="171,58 174,61 170,62" fill={c.ear} />
        <path
          d="M 166,62 Q 170,66 174,62 M 170,62 Q 170,66 170,66"
          stroke={c.coatDark}
          strokeWidth="0.9"
          fill="none"
          strokeLinecap="round"
        />
        <path
          d="M 164,64 L 148,67 M 164,66 L 150,71 M 164,62 L 146,62"
          stroke="white"
          strokeOpacity="0.5"
          strokeWidth="0.6"
          strokeLinecap="round"
        />
      </g>

      {/* Front legs */}
      <path
        id="leg_fr"
        className="landing-dcm-cat-leg-fr"
        d="M 125,95 Q 131,118 137,128 Q 140,130 138,128 Q 132,118 125,95"
        fill={`url(#${uid}-coat)`}
      />
      <path
        id="leg_br"
        className="landing-dcm-cat-leg-br"
        d="M 85,90 Q 79,118 73,128 Q 70,130 72,128 Q 78,118 85,90"
        fill={`url(#${uid}-coat)`}
      />
    </svg>
  );
};
