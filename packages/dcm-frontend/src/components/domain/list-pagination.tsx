import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '../ui/button';

export function ListPagination({
  currentPage,
  endIndex,
  hasNextPage,
  hasPreviousPage,
  onNext,
  onPrevious,
  startIndex,
  totalItems,
  totalPages,
}: {
  currentPage: number;
  endIndex: number;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  onNext: () => void;
  onPrevious: () => void;
  startIndex: number;
  totalItems: number;
  totalPages: number;
}) {
  if (totalItems === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4 text-sm text-muted-foreground">
      <span>
        {totalItems <= 1
          ? '1 item'
          : `${startIndex + 1}–${endIndex} of ${totalItems.toLocaleString('en-GB')}`}
        {totalPages > 1 ? ` · Page ${currentPage} / ${totalPages}` : ''}
      </span>
      {totalPages > 1 && (
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" disabled={!hasPreviousPage} onClick={onPrevious}>
            <ChevronLeft size={16} />
            Previous
          </Button>
          <Button variant="secondary" size="sm" disabled={!hasNextPage} onClick={onNext}>
            Next
            <ChevronRight size={16} />
          </Button>
        </div>
      )}
    </div>
  );
}
