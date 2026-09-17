import { describe, expect, it } from 'vitest';

// `import.meta.glob` is compiled away, so both arguments have to stay literal.
const stylesheets = import.meta.glob<string>('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
});
const sources = import.meta.glob<string>('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function names(text: string, pattern: RegExp): string[] {
  return [...text.matchAll(pattern)].map(([, name]) => name);
}

/**
 * A `var(--missing-token)` is dropped silently by the browser: the element renders
 * with no colour at all. That is how the "Largest cost changes" increase bars went
 * invisible — they asked for `--tdf-orange`, which no theme declares — while the
 * savings bars painted fine.
 */
describe('design tokens', () => {
  const declared = new Set<string>();
  for (const css of Object.values(stylesheets)) {
    for (const name of names(css, /(--[a-z0-9-]+)\s*:/g)) declared.add(name);
  }
  // A component may also set a local property inline, e.g. `style={{ '--deg': ... }}`.
  for (const source of Object.values(sources)) {
    for (const name of names(source, /['"](--[a-z0-9-]+)['"]\s*:/g)) declared.add(name);
  }

  it('declares every custom property referenced from a component', () => {
    const missing = new Map<string, string[]>();
    for (const [path, source] of Object.entries(sources)) {
      if (/\.test\.tsx?$/.test(path)) continue;
      for (const name of names(source, /var\(\s*(--[a-z0-9-]+)\s*[,)]/g)) {
        if (declared.has(name)) continue;
        missing.set(name, [...(missing.get(name) ?? []), path]);
      }
    }
    expect(Object.fromEntries(missing)).toEqual({});
  });

  it('found the token stylesheet, so a passing run means something', () => {
    expect(declared.has('--tdf-teal')).toBe(true);
    expect(declared.has('--warning')).toBe(true);
    expect(declared.size).toBeGreaterThan(50);
  });
});
