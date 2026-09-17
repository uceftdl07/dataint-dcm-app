import { ArrowRight, Compass, FolderPlus, MapPin, Sparkles, X, BookOpen } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTour } from '../tour/TourContext';
import { getGlobalTourStatus } from '../tour/tour-storage';
import { LandingRequestChooserModal, type LandingRequestKind } from './LandingRequestChooserModal';
import { ProjectJoinRequestModal } from './ProjectJoinRequestModal';
import { ProjectRegisterRequestModal } from './ProjectRegisterRequestModal';
import { cn } from '../lib/utils';
import './dcm-guide.css';

interface DcmGuideButtonProps {
  className?: string;
}

const MENU_ITEMS = [
  {
    id: 'welcome',
    title: 'Visit DCM',
    subtitle: 'Full cockpit tour — nav, filters, alerts (~1 min)',
    icon: Compass,
    accent: 'from-[#0055A4] to-[#00AEEF]',
    iconBg: 'bg-gradient-to-br from-tdf-blue to-tdf-teal text-white shadow-md shadow-tdf-blue/25',
    action: 'welcome' as const,
  },
  {
    id: 'page',
    title: 'This page',
    subtitle: 'Quick walkthrough of what you see right now',
    icon: MapPin,
    accent: 'from-violet-500 to-indigo-500',
    iconBg: 'bg-violet-500/10 text-violet-700',
    action: 'page' as const,
  },
  {
    id: 'lz-guide',
    title: 'LZ onboarding guide',
    subtitle: 'Azure client LZ — step-by-step',
    icon: BookOpen,
    accent: 'from-teal-600 to-cyan-600',
    iconBg: 'bg-teal-500/10 text-teal-800',
    action: 'lz-guide' as const,
  },
  {
    id: 'project',
    title: 'Join or register a project',
    subtitle: 'Create a new DCM project or join an existing one',
    icon: FolderPlus,
    accent: 'from-amber-500 to-orange-500',
    iconBg: 'bg-amber-500/10 text-amber-700',
    action: 'project' as const,
  },
];

export const DcmGuideButton: React.FC<DcmGuideButtonProps> = ({ className }) => {
  const navigate = useNavigate();
  const { startPageTour, startWelcomeTour } = useTour();
  const [menuOpen, setMenuOpen] = useState(false);
  const [projectStep, setProjectStep] = useState<'idle' | 'chooser' | LandingRequestKind>('idle');
  const [showHint, setShowHint] = useState(false);
  const [needsAttention, setNeedsAttention] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const status = getGlobalTourStatus();
    setNeedsAttention(status === 'skipped' || status === 'pending');
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [menuOpen]);

  const closeMenu = () => setMenuOpen(false);

  const runAction = (action: 'welcome' | 'page' | 'project' | 'lz-guide') => {
    closeMenu();
    setNeedsAttention(false);
    if (action === 'welcome') startWelcomeTour();
    else if (action === 'page') startPageTour();
    else if (action === 'lz-guide') navigate('/guide/lz-onboarding');
    else setProjectStep('chooser');
  };

  return (
    <>
      <div
        ref={rootRef}
        className={cn('relative', className)}
        onMouseEnter={() => setShowHint(true)}
        onMouseLeave={() => setShowHint(false)}
      >
        {showHint && !menuOpen && (
          <div
            className="dcm-guide-tooltip-bubble pointer-events-none absolute -left-2 top-1/2 z-50 hidden -translate-x-full -translate-y-1/2 pr-2 md:block"
            role="tooltip"
          >
            <div className="relative whitespace-nowrap rounded-2xl border border-tdf-blue-border/30 bg-gradient-to-r from-white to-tdf-blue-subtle/80 px-3.5 py-2 shadow-lg shadow-tdf-blue/10 backdrop-blur-sm">
              <p className="text-[11px] font-bold tracking-tight text-tdf-blue">Guide to visit DCM</p>
              <p className="text-[9px] font-medium text-slate-500">Replay anytime · tours & LZ</p>
              <span className="absolute -right-1.5 top-1/2 size-2.5 -translate-y-1/2 rotate-45 border-r border-t border-tdf-blue-border/30 bg-white" />
            </div>
          </div>
        )}

        <button
          type="button"
          data-tour="tour-help"
          onClick={() => setMenuOpen((open) => !open)}
          className={cn(
            'group relative inline-flex h-10 shrink-0 items-center gap-2 overflow-hidden rounded-2xl border px-3 shadow-sm transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tdf-blue/40',
            menuOpen
              ? 'border-tdf-blue bg-gradient-to-r from-tdf-blue to-tdf-teal text-white shadow-md shadow-tdf-blue/25'
              : 'border-tdf-blue-border/25 bg-card text-tdf-blue hover:-translate-y-0.5 hover:border-tdf-blue-border hover:shadow-md hover:shadow-tdf-blue/10 active:translate-y-0 active:scale-[0.97]',
          )}
          aria-label="DCM guides — tours and landing zone onboarding"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
        >
          {needsAttention && !menuOpen && (
            <span className="dcm-guide-trigger-pulse pointer-events-none absolute inset-0 rounded-2xl ring-2 ring-tdf-teal/40" />
          )}
          {!menuOpen && (
            <span className="dcm-guide-trigger-shimmer pointer-events-none absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100" />
          )}

          <span
            className={cn(
              'relative flex size-7 items-center justify-center rounded-xl transition-colors',
              menuOpen ? 'bg-white/20' : 'bg-tdf-blue-subtle group-hover:bg-tdf-blue/10',
            )}
          >
            <Compass
              size={15}
              className={cn(
                'transition-transform duration-500',
                menuOpen ? 'text-white' : 'text-tdf-blue group-hover:rotate-45',
              )}
            />
          </span>

          <span className="relative hidden text-xs font-bold tracking-tight sm:inline">Guide</span>

          {needsAttention && !menuOpen && (
            <span className="relative flex size-2 shrink-0 rounded-full bg-tdf-teal shadow-[0_0_8px_rgba(0,174,239,0.8)]">
              <span className="absolute inset-0 animate-ping rounded-full bg-tdf-teal opacity-60" />
            </span>
          )}
        </button>

        {menuOpen && (
          <div
            role="menu"
            className="dcm-guide-menu-panel absolute right-0 top-[calc(100%+0.65rem)] z-50 w-[min(18rem,calc(100vw-2rem))] overflow-hidden rounded-[1.35rem] border border-white/60 bg-white/95 shadow-2xl shadow-slate-950/15 backdrop-blur-xl"
          >
            <div className="relative overflow-hidden bg-gradient-to-br from-[#0055A4] via-[#0078C8] to-[#00AEEF] px-4 py-4 text-white">
              <div className="pointer-events-none absolute -right-6 -top-8 size-24 rounded-full bg-white/15 blur-2xl" />
              <div className="relative flex items-start justify-between gap-2">
                <div>
                  <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.16em]">
                    <Sparkles size={10} className="animate-pulse" />
                    DCM copilot
                  </div>
                  <p className="text-sm font-black tracking-tight">Need a hand?</p>
                  <p className="mt-0.5 text-[11px] font-medium text-white/80">
                    Pick a guide — replay as often as you like
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeMenu}
                  className="rounded-lg p-1 text-white/70 transition hover:bg-white/15 hover:text-white"
                  aria-label="Close guide menu"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="space-y-1.5 p-2">
              {MENU_ITEMS.map((item, index) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="menuitem"
                    style={{ animationDelay: `${index * 50}ms` }}
                    onClick={() => runAction(item.action)}
                    className="dcm-guide-menu-item group/item relative flex w-full items-center gap-3 overflow-hidden rounded-xl border border-transparent p-2.5 text-left transition hover:border-slate-200/80 hover:bg-slate-50/90 active:scale-[0.98]"
                  >
                    <span
                      className={cn(
                        'flex size-10 shrink-0 items-center justify-center rounded-xl transition-transform group-hover/item:scale-105',
                        item.iconBg,
                      )}
                    >
                      <Icon size={17} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="text-sm font-bold text-slate-900">{item.title}</span>
                        <ArrowRight
                          size={12}
                          className="text-slate-300 transition group-hover/item:translate-x-0.5 group-hover/item:text-tdf-blue"
                        />
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-slate-500">
                        {item.subtitle}
                      </span>
                    </span>
                    <span
                      className={cn(
                        'absolute bottom-0 left-0 h-0.5 w-0 bg-gradient-to-r transition-all duration-300 group-hover/item:w-full',
                        item.accent,
                      )}
                    />
                  </button>
                );
              })}
            </div>

            <p className="border-t border-slate-100 px-4 py-2.5 text-center text-[9px] font-medium uppercase tracking-[0.12em] text-slate-400">
              Closed the welcome tour? You&apos;re in the right place
            </p>
          </div>
        )}
      </div>

      {projectStep === 'chooser' && (
        <LandingRequestChooserModal
          onClose={() => setProjectStep('idle')}
          onChoose={(kind) => setProjectStep(kind)}
        />
      )}
      {projectStep === 'project_register' && (
        <ProjectRegisterRequestModal
          onClose={() => setProjectStep('idle')}
          onSwitchToJoin={() => setProjectStep('project_join')}
        />
      )}
      {projectStep === 'project_join' && (
        <ProjectJoinRequestModal
          onClose={() => setProjectStep('idle')}
          onSwitchToRegister={() => setProjectStep('project_register')}
        />
      )}
    </>
  );
};
