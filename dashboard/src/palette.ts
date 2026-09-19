// Chart libraries need literal color values, not CSS custom properties, in
// their SVG props — this mirrors theme.css hex-for-hex so the two never
// drift. If you change one, change the other.

export interface ChartPalette {
  surface1: string;
  gridline: string;
  baseline: string;
  textMuted: string;
  textSecondary: string;
  series: [string, string, string, string, string, string, string, string];
  divergingPositive: string;
  divergingNegative: string;
  divergingNeutral: string;
}

export const LIGHT_PALETTE: ChartPalette = {
  surface1: "#fcfcfb",
  gridline: "#e1e0d9",
  baseline: "#c3c2b7",
  textMuted: "#898781",
  textSecondary: "#52514e",
  series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
  divergingPositive: "#2a78d6",
  divergingNegative: "#e34948",
  divergingNeutral: "#f0efec",
};

export const DARK_PALETTE: ChartPalette = {
  surface1: "#1a1a19",
  gridline: "#2c2c2a",
  baseline: "#383835",
  textMuted: "#898781",
  textSecondary: "#c3c2b7",
  series: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
  divergingPositive: "#3987e5",
  divergingNegative: "#e66767",
  divergingNeutral: "#383835",
};
