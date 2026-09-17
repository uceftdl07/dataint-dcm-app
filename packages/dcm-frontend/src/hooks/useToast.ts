/**
 * useToast — Hook for displaying toast notifications
 * 
 * Usage:
 * ```tsx
 * const toast = useToast();
 * 
 * toast.showError('Error', 'Unable to connect');
 * toast.showSuccess('Success', 'Authentication successful');
 * ```
 */

import { useContext } from 'react';
import { ToastContext } from '../contexts/toast';

export const useToast = () => {
  const context = useContext(ToastContext);
  
  if (!context) {
    throw new Error('useToast must be used inside a ToastProvider');
  }
  
  return context;
};
