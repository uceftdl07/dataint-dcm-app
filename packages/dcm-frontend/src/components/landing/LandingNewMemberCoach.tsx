import { ArrowRight, MessageSquare, X } from 'lucide-react';
import React from 'react';

interface LandingNewMemberCoachProps {
  open: boolean;
  onClose: () => void;
  onRequestAccess: () => void;
}

const DCM_ACCESS_STEPS = [
  'Sign in with Microsoft SSO on this page.',
  'Fill in the DCM access request form (justification + optional landing zones).',
  'Submit — admins receive a notification in the Teams channel.',
  'Wait for approval by email, then sign in again to open the cockpit.',
];

const LZ_ACCESS_STEPS = [
  'Already in DCM but missing a landing zone?',
  'Sign in → open My Landing Zones.',
  'Click Request access on the zone you need.',
  'Submit — admins are notified on Teams, same approval flow.',
];

export const LandingNewMemberCoach: React.FC<LandingNewMemberCoachProps> = ({
  open,
  onClose,
  onRequestAccess,
}) => {
  if (!open) return null;

  return (
    <div
      className="landing-coach-root fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/40 p-4 backdrop-blur-[2px] sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="landing-coach-title"
    >
      <div className="landing-coach-panel relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-[1.35rem] border border-white/70 bg-white/98 p-5 shadow-2xl">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          aria-label="Close guide"
        >
          <X size={18} />
        </button>

        <div className="pr-8">
          <div className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-[#0055A4]">
            <MessageSquare size={12} />
            Access guide
          </div>
          <h3 id="landing-coach-title" className="text-lg font-black text-slate-900">
            How to request DCM access
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            The app already includes request forms — they notify administrators on a Teams channel.
          </p>
        </div>

        <div className="mt-5 space-y-4">
          <section className="rounded-xl border border-[#0055A4]/20 bg-blue-50/50 p-4">
            <h4 className="text-xs font-black uppercase tracking-[0.14em] text-[#0055A4]">
              New to DCM (no account yet)
            </h4>
            <ol className="mt-3 space-y-2">
              {DCM_ACCESS_STEPS.map((step, index) => (
                <li key={step} className="flex gap-2 text-sm text-slate-700">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[#0055A4] text-[10px] font-bold text-white">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <h4 className="text-xs font-black uppercase tracking-[0.14em] text-slate-700">
              Already in DCM — need a landing zone?
            </h4>
            <ol className="mt-3 space-y-2">
              {LZ_ACCESS_STEPS.map((step, index) => (
                <li key={step} className="flex gap-2 text-sm text-slate-600">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-slate-300 text-[10px] font-bold text-slate-800">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="mt-5 flex flex-col gap-2">
          <button
            type="button"
            onClick={onRequestAccess}
            className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0055A4] to-[#00AEEF] px-4 py-3.5 text-[11px] font-black uppercase tracking-[0.14em] text-white shadow-lg transition hover:scale-[1.01] active:scale-[0.99]"
          >
            Sign in & open DCM access form
            <ArrowRight size={15} className="transition group-hover:translate-x-1" />
          </button>
          <p className="text-center text-[10px] font-medium text-slate-500">
            Uses the existing Request DCM Access popup · Teams notification to admins
          </p>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl py-2.5 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500 transition hover:bg-slate-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
