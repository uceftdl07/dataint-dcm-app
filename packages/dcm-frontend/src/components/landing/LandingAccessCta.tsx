import { ArrowRight, Layers } from 'lucide-react';
import React from 'react';

interface LandingAccessCtaProps {
  onOpenForm: () => void;
}

/** Fixed CTA — request onboarding of a new Landing Zone in DCM. */
export const LandingAccessCta: React.FC<LandingAccessCtaProps> = ({ onOpenForm }) => {
  return (
    <div className="landing-access-cta-root fixed bottom-4 right-4 z-[55] sm:bottom-6 sm:right-6">
      <button
        type="button"
        onClick={onOpenForm}
        className="landing-access-cta group w-[min(100vw-2rem,21rem)] rounded-[1.35rem] border border-white/70 bg-white/90 p-5 text-left shadow-xl outline-none backdrop-blur-xl transition hover:border-[#0055A4]/25 hover:shadow-2xl focus-visible:ring-2 focus-visible:ring-[#0055A4] focus-visible:ring-offset-2 sm:w-[22rem] sm:p-6"
        aria-label="Join or register a DCM project"
      >
        <div className="landing-access-cta-brand flex items-center gap-3 border-b border-slate-200/80 pb-4">
          <img
            src="/images/compagny-logo.png"
            alt=""
            className="landing-access-cta-logo"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-black tracking-tight text-slate-900 sm:text-base">
              Data <span className="text-[#0055A4]">connect</span>
            </p>
            <p className="mt-0.5 text-[9px] font-black uppercase tracking-[0.28em] text-slate-500 sm:text-[10px]">
              Project registration
            </p>
          </div>
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-700 transition group-hover:bg-indigo-500/15">
            <Layers className="size-4" strokeWidth={2.25} />
          </span>
        </div>

        <p className="mt-4 text-xs font-black uppercase tracking-[0.18em] text-[#0055A4] sm:text-sm">
          No project yet?
        </p>
        <p className="mt-2 text-[11px] font-bold leading-relaxed text-slate-600 sm:text-xs">
          Join an existing DCM project or register a new one — admins receive a Teams notification.
        </p>

        <span className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#0055A4] px-4 py-3 text-[10px] font-black uppercase tracking-[0.16em] text-white shadow-md transition group-hover:bg-[#004483] sm:text-[11px]">
          Join or register project
          <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
        </span>
      </button>
    </div>
  );
};
