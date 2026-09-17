import { Sparkles, X } from 'lucide-react';
import React from 'react';
import { Button } from '../components/ui/button';

interface WelcomeTourModalProps {
  onAccept: () => void;
  onDecline: () => void;
}

export const WelcomeTourModal: React.FC<WelcomeTourModalProps> = ({ onAccept, onDecline }) => (
  <div
    className="dcm-tour-modal-backdrop fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-labelledby="welcome-tour-title"
  >
    <div className="dcm-tour-modal-panel relative w-full max-w-md overflow-hidden rounded-2xl border border-border bg-card p-6 shadow-2xl">
      <button
        type="button"
        onClick={onDecline}
        className="absolute right-4 top-4 rounded-lg p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        aria-label="Close"
      >
        <X size={18} />
      </button>

      <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
        <Sparkles size={14} className="animate-pulse" />
        Interactive guide
      </div>

      <h2 id="welcome-tour-title" className="text-xl font-bold tracking-tight text-foreground">
        Welcome to Data connect
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        Would you like a quick animated tour of navigation, filters, and key features? It takes about one
        minute. You can replay it anytime from the guide button in the header.
      </p>

      <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={onDecline}>
          Maybe later
        </Button>
        <Button onClick={onAccept} className="bg-gradient-to-r from-tdf-blue to-tdf-teal text-white">
          Start guided tour
        </Button>
      </div>
    </div>
  </div>
);
