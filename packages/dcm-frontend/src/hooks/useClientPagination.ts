import { useEffect, useMemo, useState } from 'react';

export interface ClientPaginationResult<T> {
  currentPage: number;
  endIndex: number;
  goToPage: (page: number) => void;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  nextPage: () => void;
  pageItems: T[];
  pageSize: number;
  previousPage: () => void;
  startIndex: number;
  totalItems: number;
  totalPages: number;
}

export function useClientPagination<T>(
  items: T[],
  pageSize = 10,
): ClientPaginationResult<T> {
  const [currentPage, setCurrentPage] = useState(1);
  const totalItems = items.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  useEffect(() => {
    setCurrentPage(1);
  }, [totalItems, pageSize]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalItems);
  const pageItems = useMemo(
    () => items.slice(startIndex, startIndex + pageSize),
    [items, startIndex, pageSize],
  );

  const goToPage = (page: number) => {
    setCurrentPage(Math.min(Math.max(1, page), totalPages));
  };

  return {
    currentPage,
    endIndex,
    goToPage,
    hasNextPage: currentPage < totalPages,
    hasPreviousPage: currentPage > 1,
    nextPage: () => goToPage(currentPage + 1),
    pageItems,
    pageSize,
    previousPage: () => goToPage(currentPage - 1),
    startIndex,
    totalItems,
    totalPages,
  };
}
