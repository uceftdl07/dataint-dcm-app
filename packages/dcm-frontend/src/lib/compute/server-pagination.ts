/**
 * Pagination footer props for a table whose page is cut by the server.
 *
 * The compute tables all take the same `pagination` prop, and a server-paged one
 * cannot use `useClientPagination`: the rows it holds *are* the page, so slicing
 * them again would show 25 of 25 and report a total of 25 out of 1.4 M.
 */

export interface ServerPage {
  /** Rows matching the filters across every page. */
  total: number;
  page: number;
  page_size: number;
  /** Rows actually returned for this page — the last page is usually shorter. */
  itemCount: number;
}

export interface ServerPaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  startIndex: number;
  endIndex: number;
  hasPreviousPage: boolean;
  hasNextPage: boolean;
  onPrevious: () => void;
  onNext: () => void;
}

/**
 * `page` is echoed by the response, not read from local state: while a page change
 * is in flight the footer keeps describing the rows on screen instead of jumping
 * ahead of them. `fallbackPage` covers the first render, when there is no response.
 */
export function serverPaginationProps(
  page: ServerPage | null | undefined,
  fallbackPage: number,
  setPage: (next: (current: number) => number) => void
): ServerPaginationProps {
  const currentPage = page?.page ?? fallbackPage;
  const pageSize = page?.page_size ?? 0;
  const total = page?.total ?? 0;
  const startIndex = (currentPage - 1) * pageSize;

  return {
    currentPage,
    totalPages: pageSize > 0 ? Math.max(1, Math.ceil(total / pageSize)) : 1,
    totalItems: total,
    startIndex,
    endIndex: Math.min(startIndex + (page?.itemCount ?? 0), total),
    hasPreviousPage: currentPage > 1,
    hasNextPage: currentPage * pageSize < total,
    onPrevious: () => setPage((current) => Math.max(1, current - 1)),
    onNext: () => setPage((current) => current + 1),
  };
}
