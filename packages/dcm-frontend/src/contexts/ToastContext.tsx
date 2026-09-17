/**
 * ToastContext — Global toast notification system
 * 
 * Provides visual notifications for successes, errors, warnings, and info messages.
 */

import React, { useCallback, useState } from 'react';
import { AlertCircle, CheckCircle, Info, X, XCircle } from 'lucide-react';
import { ToastContext, type Toast, type ToastContextValue, type ToastType } from './toast';

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (type: ToastType, title: string, message?: string, duration: number = 5000) => {
      const id = `toast-${Date.now()}-${Math.random()}`;
      const newToast: Toast = { id, type, title, message, duration };

      setToasts((prev) => [...prev, newToast]);

      // Auto-remove after duration
      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }
    },
    [removeToast]
  );

  const showSuccess = useCallback(
    (title: string, message?: string) => showToast('success', title, message),
    [showToast]
  );

  const showError = useCallback(
    (title: string, message?: string) => showToast('error', title, message, 7000), // Longer for errors
    [showToast]
  );

  const showWarning = useCallback(
    (title: string, message?: string) => showToast('warning', title, message),
    [showToast]
  );

  const showInfo = useCallback(
    (title: string, message?: string) => showToast('info', title, message),
    [showToast]
  );

  const value: ToastContextValue = {
    showToast,
    showSuccess,
    showError,
    showWarning,
    showInfo,
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  );
};

// Toast Container Component
interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: string) => void;
}

const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onRemove }) => {
  return (
    <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-3 pointer-events-none">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  );
};

// Individual Toast Item
interface ToastItemProps {
  toast: Toast;
  onRemove: (id: string) => void;
}

const ToastItem: React.FC<ToastItemProps> = ({ toast, onRemove }) => {
  const [isExiting, setIsExiting] = React.useState(false);

  const handleClose = () => {
    setIsExiting(true);
    setTimeout(() => {
      onRemove(toast.id);
    }, 300); // Match animation duration
  };

  const config = {
    success: {
      icon: CheckCircle,
      bgColor: 'bg-emerald-50',
      borderColor: 'border-emerald-200',
      iconColor: 'text-emerald-600',
      textColor: 'text-emerald-900',
    },
    error: {
      icon: XCircle,
      bgColor: 'bg-red-50',
      borderColor: 'border-red-200',
      iconColor: 'text-red-600',
      textColor: 'text-red-900',
    },
    warning: {
      icon: AlertCircle,
      bgColor: 'bg-amber-50',
      borderColor: 'border-amber-200',
      iconColor: 'text-amber-600',
      textColor: 'text-amber-900',
    },
    info: {
      icon: Info,
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      iconColor: 'text-blue-600',
      textColor: 'text-blue-900',
    },
  };

  const { icon: Icon, bgColor, borderColor, iconColor, textColor } = config[toast.type];

  return (
    <div
      className={`
        pointer-events-auto
        min-w-[320px] max-w-md
        ${bgColor} ${borderColor} border
        rounded-xl shadow-lg
        p-4
        flex items-start gap-3
        transform transition-all duration-300 ease-out
        ${isExiting ? 'translate-x-[120%] opacity-0' : 'translate-x-0 opacity-100'}
      `}
    >
      {/* Icon */}
      <div className={`flex-shrink-0 ${iconColor}`}>
        <Icon size={20} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <h4 className={`text-sm font-bold ${textColor} mb-1`}>{toast.title}</h4>
        {toast.message && (
          <p className={`text-xs ${textColor}`}>{toast.message}</p>
        )}
      </div>

      {/* Close button */}
      <button
        onClick={handleClose}
        className={`flex-shrink-0 ${iconColor} hover:opacity-70 transition-opacity`}
      >
        <X size={16} />
      </button>
    </div>
  );
};
