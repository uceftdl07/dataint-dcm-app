import { createContext, useContext } from 'react';

export interface TimeRangeState {
  startDate: string;
  endDate: string;
  description: string;
}

export interface TimeRangeContextType {
  timeRange: TimeRangeState;
  updateTimeRange: (startDate: string, endDate: string, description: string) => void;
  resetToDefault: () => void;
  getDaysCount: () => number;
  isValidRange: () => boolean;
  getApiParams: () => { start_date: string; end_date: string };
  getDisplayRange: () => {
    startDate: string;
    endDate: string;
    description: string;
    daysCount: number;
  };
}

export const TimeRangeContext = createContext<TimeRangeContextType | undefined>(undefined);

export const useGlobalTimeRange = (): TimeRangeContextType => {
  const context = useContext(TimeRangeContext);
  if (context === undefined) {
    throw new Error('useGlobalTimeRange must be used within a TimeRangeProvider');
  }
  return context;
};

