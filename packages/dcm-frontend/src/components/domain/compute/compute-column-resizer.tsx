import { useRef } from 'react';
import { cn } from '../../../lib/utils';
import { KEYBOARD_RESIZE_STEP } from '../../../hooks/useColumnWidths';

/**
 * Poignée de redimensionnement d'une colonne, posée sur le bord droit de sa
 * cellule d'en-tête.
 *
 * La cellule d'en-tête porte déjà le bouton de tri : chaque geste est arrêté ici
 * (`stopPropagation`) pour qu'un glissement ne trie pas la colonne au relâchement.
 */
export function ComputeColumnResizer({
  columnLabel,
  width,
  min,
  max,
  onResize,
  onReset,
  locale = 'fr',
}: {
  /** Nom lisible de la colonne, pour l'annonce vocale de la poignée. */
  columnLabel: string;
  locale?: 'fr' | 'en';
  width: number;
  min: number;
  max: number;
  onResize: (width: number) => void;
  onReset: () => void;
}) {
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={`${locale === 'en' ? 'Resize column' : 'Redimensionner la colonne'} ${columnLabel}`}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      data-testid={`column-resizer-${columnLabel}`}
      className={cn(
        'absolute inset-y-0 right-0 z-10 w-2 cursor-col-resize touch-none select-none',
        'after:absolute after:inset-y-1 after:right-0 after:w-px after:bg-border after:content-[""]',
        'hover:after:bg-primary focus-visible:outline-none focus-visible:after:bg-primary focus-visible:after:w-0.5'
      )}
      onClick={(event) => {
        // Un clic sur la poignée n'est pas un clic sur l'en-tête.
        event.stopPropagation();
        event.preventDefault();
      }}
      onPointerDown={(event) => {
        if (event.button !== 0) {
          return;
        }
        event.stopPropagation();
        event.preventDefault();
        drag.current = { startX: event.clientX, startWidth: width };
        // Capture facultative : absente de jsdom, et le glissement reste correct
        // sans elle puisque les gestionnaires vivent sur cet élément.
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!drag.current) {
          return;
        }
        event.stopPropagation();
        onResize(drag.current.startWidth + (event.clientX - drag.current.startX));
      }}
      onPointerUp={(event) => {
        if (!drag.current) {
          return;
        }
        event.stopPropagation();
        drag.current = null;
        event.currentTarget.releasePointerCapture?.(event.pointerId);
      }}
      onPointerCancel={() => {
        drag.current = null;
      }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          event.stopPropagation();
          onResize(width - KEYBOARD_RESIZE_STEP);
          return;
        }
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          event.stopPropagation();
          onResize(width + KEYBOARD_RESIZE_STEP);
          return;
        }
        if (event.key === 'Home') {
          event.preventDefault();
          event.stopPropagation();
          onReset();
        }
      }}
    />
  );
}
