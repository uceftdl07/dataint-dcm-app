import React, { useState } from 'react';
import { LandingDcmCat } from './LandingDcmCat';

interface LandingWalkingGuideProps {
  onOpenForm: () => void;
}

export const LandingWalkingGuide: React.FC<LandingWalkingGuideProps> = ({ onOpenForm }) => {
  const [hovered, setHovered] = useState(false);
  const [clicked, setClicked] = useState(false);

  const handleClick = () => {
    setClicked(true);
    window.setTimeout(() => setClicked(false), 420);
    onOpenForm();
  };

  return (
    <div className="landing-dcm-cat-track pointer-events-none fixed bottom-2 left-0 z-[55] h-52 w-full overflow-visible sm:bottom-3">
      <div className="landing-dcm-cat-path pointer-events-none">
        <button
          type="button"
          onClick={handleClick}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          className="landing-dcm-cat-trigger group pointer-events-auto flex flex-col items-center border-0 bg-transparent p-0 outline-none focus-visible:ring-2 focus-visible:ring-[#0055A4] focus-visible:ring-offset-2"
          aria-label="No DCM access? Open the access request guide"
          title="No DCM access yet? Click me — I'll guide you through the request."
        >
          <div
            className={`landing-dcm-cat-bubble mb-2 w-[min(100vw-2rem,20.5rem)] rounded-[1.25rem] px-5 py-4 text-center transition-all duration-300 sm:w-[21.5rem] sm:rounded-[1.35rem] sm:px-6 sm:py-5 ${
              hovered ? 'landing-dcm-cat-bubble-active scale-[1.02]' : ''
            }`}
          >
            <div className="landing-dcm-cat-bubble-brand">
              <img
                src="/images/compagny-logo.png"
                alt=""
                className="landing-dcm-cat-brand-logo"
                aria-hidden
              />
              <div className="min-w-0 flex-1 text-left">
                <p className="truncate text-sm font-black tracking-tight text-slate-900 sm:text-base">
                  Data <span className="text-[#0055A4]">connect</span>
                </p>
                <p className="mt-0.5 text-[9px] font-black uppercase tracking-[0.28em] text-slate-500 sm:text-[10px]">
                  Access guide
                </p>
              </div>
            </div>
            <p className="landing-dcm-cat-bubble-title mt-4 text-xs font-black uppercase leading-snug tracking-[0.16em] text-[#0055A4] sm:mt-5 sm:text-sm sm:tracking-[0.18em]">
              No DCM access yet?
            </p>
            <p className="landing-dcm-cat-bubble-body mt-2 text-[11px] font-bold leading-relaxed text-slate-600 sm:text-xs sm:leading-relaxed">
              Click me — I&apos;ll guide you through the request.
            </p>
          </div>

          <div className="landing-dcm-cat-figure">
            <div className="landing-dcm-cat-flip">
              <LandingDcmCat hovered={hovered} clicked={clicked} />
            </div>
          </div>
        </button>
      </div>
    </div>
  );
};
