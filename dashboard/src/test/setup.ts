import "@testing-library/jest-dom/vitest";

// recharts' ResponsiveContainer needs a ResizeObserver, which jsdom doesn't
// implement. A no-op stub is enough — these tests assert on the always-
// rendered table view, not on chart pixel dimensions.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).ResizeObserver ??= ResizeObserverStub;

// jsdom doesn't implement matchMedia. useChartPalette only reads .matches
// and listens for "change" — this stub covers exactly that, nothing more.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
