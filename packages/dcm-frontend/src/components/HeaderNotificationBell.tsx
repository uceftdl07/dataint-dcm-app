import { Bell, Loader2, Settings } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { useHeaderNotifications } from '../hooks/useHeaderNotifications';
import { cn } from '../lib/utils';
import type { AlertSeverity } from '../types/api';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

const severityVariant: Record<AlertSeverity, 'destructive' | 'warning' | 'info' | 'secondary'> = {
  critical: 'destructive',
  high: 'warning',
  medium: 'info',
  low: 'secondary',
};

const PANEL_MAX_WIDTH = 352;
const PANEL_VIEWPORT_MARGIN = 8;

function formatDetectedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface HeaderNotificationBellProps {
  buttonClassName?: string;
}

export const HeaderNotificationBell: React.FC<HeaderNotificationBellProps> = ({
  buttonClassName,
}) => {
  const { items, unreadCount, loading, error, markAsRead, refresh } = useHeaderNotifications();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties>({});

  useEffect(() => {
    if (open) {
      void refresh();
    }
  }, [open, refresh]);

  useEffect(() => {
    if (!open || !buttonRef.current) {
      return undefined;
    }

    const updatePosition = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;

      const panelWidth = Math.min(PANEL_MAX_WIDTH, window.innerWidth - PANEL_VIEWPORT_MARGIN * 2);
      let left = rect.left;
      if (left + panelWidth > window.innerWidth - PANEL_VIEWPORT_MARGIN) {
        left = window.innerWidth - panelWidth - PANEL_VIEWPORT_MARGIN;
      }

      setPanelStyle({
        position: 'fixed',
        top: rect.bottom + 8,
        left: Math.max(PANEL_VIEWPORT_MARGIN, left),
        width: panelWidth,
        zIndex: 120,
      });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);

    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || buttonRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const countLabel = unreadCount > 9 ? '9+' : String(unreadCount);

  const panel = open ? (
    <div
      ref={panelRef}
      role="dialog"
      aria-label="Notification center"
      style={panelStyle}
      className="overflow-hidden rounded-2xl border bg-popover text-popover-foreground shadow-2xl shadow-slate-950/15 ring-1 ring-border"
    >
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Notifications</p>
          <p className="text-xs text-muted-foreground">Active alerts for your scope</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 px-2"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Refresh notifications"
        >
          <Loader2 className={cn('size-4', loading && 'animate-spin')} />
        </Button>
      </div>

      <div className="max-h-80 overflow-y-auto">
        {loading && items.length === 0 ? (
          <p className="flex items-center gap-2 px-4 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading notifications...
          </p>
        ) : error ? (
          <p className="px-4 py-6 text-sm text-destructive">{error}</p>
        ) : items.length === 0 ? (
          <p className="px-4 py-6 text-sm text-muted-foreground">
            No active alerts match your notification preferences.
          </p>
        ) : (
          <ul className="divide-y">
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  to={item.href}
                  onClick={() => {
                    markAsRead(item.id, item.sourceLzId);
                    setOpen(false);
                  }}
                  className={cn(
                    'block px-4 py-3 transition hover:bg-accent/60',
                    !item.read && 'bg-primary/[0.03]',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 text-sm font-medium text-foreground">{item.title}</p>
                    <Badge variant={severityVariant[item.severity]} className="shrink-0 capitalize">
                      {item.severity}
                    </Badge>
                  </div>
                  {item.description ? (
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {item.description}
                    </p>
                  ) : null}
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Security · {formatDetectedAt(item.detectedAt)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t bg-muted/30 px-4 py-3">
        <Link
          to="/alerts"
          onClick={() => setOpen(false)}
          className="text-xs font-semibold text-primary hover:underline"
        >
          View all alerts
        </Link>
        <Link
          to="/settings"
          onClick={() => setOpen(false)}
          className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <Settings size={12} />
          Preferences
        </Link>
      </div>
    </div>
  ) : null;

  return (
    <div className="relative shrink-0">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn(
          buttonClassName ??
            'relative inline-flex size-9 items-center justify-center rounded-full text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          open && 'border-tdf-blue-border bg-tdf-blue-subtle/80 text-tdf-blue',
        )}
        aria-label={
          unreadCount > 0
            ? `Notifications, ${unreadCount} active alert${unreadCount === 1 ? '' : 's'}`
            : 'Notifications'
        }
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Notifications"
      >
        <Bell size={18} />
        {unreadCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-[1.125rem] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold leading-none text-destructive-foreground">
            {countLabel}
          </span>
        ) : null}
      </button>

      {panel && typeof document !== 'undefined' ? createPortal(panel, document.body) : null}
    </div>
  );
};
