import { useCallback, useRef, useState } from 'react';

export function getScrollBehavior(): ScrollBehavior {
  if (typeof window === 'undefined') {
    return 'auto';
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
}

export function useMetricSectionFocus<T extends string>() {
  const [activeSection, setActiveSection] = useState<T | null>(null);
  const sectionRefs = useRef<Map<T, HTMLElement>>(new Map());

  const bindSectionRef = useCallback(
    (sectionId: T) => (node: HTMLElement | null) => {
      if (node) {
        sectionRefs.current.set(sectionId, node);
      } else {
        sectionRefs.current.delete(sectionId);
      }
    },
    [],
  );

  const scrollToSection = useCallback((sectionId: T) => {
    const element = sectionRefs.current.get(sectionId);
    if (!element) {
      return;
    }
    element.scrollIntoView({ behavior: getScrollBehavior(), block: 'start' });
    element.focus({ preventScroll: true });
  }, []);

  const focusSection = useCallback(
    (sectionId: T) => {
      setActiveSection((current) => {
        const next = current === sectionId ? null : sectionId;
        if (next) {
          requestAnimationFrame(() => scrollToSection(next));
        }
        return next;
      });
    },
    [scrollToSection],
  );

  const clearFocus = useCallback(() => {
    setActiveSection(null);
  }, []);

  const isSectionActive = useCallback(
    (sectionId: T) => activeSection === sectionId,
    [activeSection],
  );

  return {
    activeSection,
    bindSectionRef,
    clearFocus,
    focusSection,
    isSectionActive,
    scrollToSection,
  };
}
