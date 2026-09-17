import React from 'react';
import { DATAIQ_BRAND } from '../config/dataiq';
import { cn } from '../lib/utils';

const sizeMap = {
  xs: 'size-8',
  sm: 'size-10',
  md: 'size-12',
  lg: 'size-16',
  xl: 'size-32 sm:size-36',
  hero: 'size-44 sm:size-52 2xl:size-56',
} as const;

const padMap: Record<keyof typeof sizeMap, string> = {
  xs: 'p-0.5',
  sm: 'p-1',
  md: 'p-1',
  lg: 'p-1.5',
  xl: 'p-2.5',
  hero: 'p-3 sm:p-3.5',
};

export type DataIQAvatarSize = keyof typeof sizeMap;

interface DataIQAvatarProps {
  size?: DataIQAvatarSize;
  className?: string;
  ring?: boolean;
}

/** Circular badge: white background, blue mascot + DataIQ legend. */
export const DataIQAvatar: React.FC<DataIQAvatarProps> = ({
  size = 'md',
  className,
  ring = false,
}) => (
  <div
    className={cn(
      'relative flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-white shadow-sm',
      sizeMap[size],
      padMap[size],
      ring && 'ring-2 ring-primary/20 ring-offset-2 ring-offset-background',
      className,
    )}
  >
    <img
      src={DATAIQ_BRAND.logoSrc}
      alt={DATAIQ_BRAND.name}
      className="max-h-full max-w-full object-contain"
      draggable={false}
    />
  </div>
);
