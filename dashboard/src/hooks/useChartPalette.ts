import { useEffect, useState } from "react";
import { DARK_PALETTE, LIGHT_PALETTE, type ChartPalette } from "../palette";

/** Tracks the OS color-scheme preference so charts pick the validated dark-mode steps, not an automatic filter/invert. */
export function useChartPalette(): ChartPalette {
  const [isDark, setIsDark] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (event: MediaQueryListEvent) => setIsDark(event.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  return isDark ? DARK_PALETTE : LIGHT_PALETTE;
}
