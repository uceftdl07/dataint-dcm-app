/**
 * Global time range context — shared across all DCM pages.
 * Preserved from the POC with adaptation for DCM API params naming (snake_case).
 */

import React, { useCallback, useState, type ReactNode } from 'react';
import { TimeRangeContext, type TimeRangeContextType, type TimeRangeState } from './time-range';

interface TimeRangeProviderProps {
  children: ReactNode;
  defaultDays?: number;
}

export const TimeRangeProvider: React.FC<TimeRangeProviderProps> = ({
  children,
  defaultDays = 30,
}) => {
  const getDefaultRange = useCallback(
    (days: number): TimeRangeState => {
      const endDate = new Date();
      const startDate = new Date(endDate.getTime() - days * 24 * 60 * 60 * 1000);
      return {
        startDate: startDate.toISOString().split('T')[0],
        endDate: endDate.toISOString().split('T')[0],
        description: `${days} days`,
      };
    },
    [],
  );

  const [timeRange, setTimeRange] = useState<TimeRangeState>(() => getDefaultRange(defaultDays));

  const updateTimeRange = useCallback((startDate: string, endDate: string, description: string) => {
    setTimeRange({ startDate, endDate, description });
  }, []);

  const resetToDefault = useCallback(() => {
    setTimeRange(getDefaultRange(defaultDays));
  }, [defaultDays, getDefaultRange]);

  const getDaysCount = useCallback(() => {
    const start = new Date(timeRange.startDate);
    const end = new Date(timeRange.endDate);
    return Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
  }, [timeRange]);

  const isValidRange = useCallback(() => {
    const start = new Date(timeRange.startDate);
    const end = new Date(timeRange.endDate);
    return start <= end && end <= new Date();
  }, [timeRange]);

  const getApiParams = useCallback(() => {
    return { start_date: timeRange.startDate, end_date: timeRange.endDate };
  }, [timeRange]);

  const getDisplayRange = useCallback(() => {
    const start = new Date(timeRange.startDate);
    const end = new Date(timeRange.endDate);
    return {
      startDate: start.toLocaleDateString('en-GB'),
      endDate: end.toLocaleDateString('en-GB'),
      description: timeRange.description,
      daysCount: getDaysCount(),
    };
  }, [timeRange, getDaysCount]);

  const value: TimeRangeContextType = {
    timeRange,
    updateTimeRange,
    resetToDefault,
    getDaysCount,
    isValidRange,
    getApiParams,
    getDisplayRange,
  };

  return <TimeRangeContext.Provider value={value}>{children}</TimeRangeContext.Provider>;
};
