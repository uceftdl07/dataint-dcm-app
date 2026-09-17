import React from 'react';
import { cn } from '../lib/utils';
import { TotalEnergiesIcon } from './icons/te';

interface FooterProps {
  variant?: 'app' | 'landing';
}

const FOOTER_LINKS = [
  {
    title: 'Network',
    links: ['Portail CCoE', 'Technical support'],
  },
  {
    title: 'Governance',
    links: ['Security', 'Legal Hub'],
  },
];

const Footer: React.FC<FooterProps> = ({ variant = 'app' }) => {
  const isLanding = variant === 'landing';

  return (
    <footer
      className={cn(
        'relative overflow-hidden pointer-events-auto',
        isLanding
          ? 'mt-40 border-t-4 border-slate-200 bg-[#f8fafc] px-6 py-12 text-slate-900 md:mt-60 md:px-8'
          : 'border-t border-border bg-card/70 px-4 py-8 text-foreground sm:px-6 lg:px-8',
      )}
    >
      <div className={cn('mx-auto grid grid-cols-1 gap-10 text-left', isLanding ? 'max-w-7xl font-bold sm:grid-cols-2 md:grid-cols-4' : 'max-w-[1600px] md:grid-cols-[1fr_auto_auto]')}>
        <div className={cn('space-y-5', isLanding ? 'col-span-1 font-bold sm:col-span-2 md:space-y-8' : 'max-w-md')}>
          <div className="flex items-center gap-4">
            <div className={cn('flex items-center justify-center rounded-xl border bg-white shadow-lg', isLanding ? 'h-10 w-10 border-slate-200 md:h-12 md:w-12' : 'size-11 border-border')}>
              {isLanding ? (
                <img src="/images/compagny-logo.png" alt="Company Logo" className="h-6 w-6 object-contain md:h-7 md:w-7" />
              ) : (
                <TotalEnergiesIcon className="h-6 w-8" />
              )}
            </div>
            <span className={cn('font-black tracking-tighter italic', isLanding ? 'text-xl text-slate-900 md:text-2xl' : 'text-lg text-foreground')}>
              Data <span className={isLanding ? 'text-[#0055A4]' : 'text-primary'}>connect</span>
            </span>
          </div>
          <p className={cn('max-w-sm text-sm leading-relaxed', isLanding ? 'font-black text-slate-600' : 'text-muted-foreground')}>
            Strategic group infra-data monitoring solution.
          </p>
        </div>

        {FOOTER_LINKS.map((group) => (
          <div key={group.title}>
            <h4 className={cn('mb-4 text-[9px] font-black uppercase tracking-[0.3em]', isLanding ? 'text-slate-900 md:mb-6' : 'text-muted-foreground')}>
              {group.title}
            </h4>
            <ul className={cn('space-y-3 text-xs uppercase tracking-widest', isLanding ? 'font-black text-slate-500 md:space-y-4' : 'font-semibold text-muted-foreground')}>
              {group.links.map((link) => (
                <li key={link}>
                  <a href="#" className={cn('transition-colors', isLanding ? 'hover:text-blue-600' : 'hover:text-primary')}>
                    {link}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className={cn('mx-auto mt-10 flex flex-col items-center justify-between gap-4 border-t pt-6 md:flex-row', isLanding ? 'max-w-7xl border-slate-300 font-bold md:mt-12 md:pt-8' : 'max-w-[1600px] border-border')}>
        <p className={cn('text-center text-[9px] font-black uppercase tracking-[0.35em]', isLanding ? 'text-slate-700 md:tracking-[0.4em]' : 'text-muted-foreground')}>
          © 2026 Data connect — Exclusive property of the group
        </p>
        <div className={cn('rounded-full px-4 py-1.5 text-[9px] font-black uppercase tracking-widest shadow-lg', isLanding ? 'bg-slate-900 text-white' : 'bg-primary text-primary-foreground')}>
          Version stable
        </div>
      </div>
    </footer>
  );
};

export default Footer;
