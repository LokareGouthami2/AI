/** Handwriting render settings: defaults and a cleaner that guarantees the
 * server always receives a complete, in-range settings object (the server
 * rejects anything else, which used to fail Preview and Final PDF). */

export const DEFAULT_SETTINGS = {
  style: 'quick',
  ink: 'blue',
  paper: 'ruled',
  page_size: 'A4',
  font_size: 16,
  line_spacing: 1.6,
  paragraph_spacing: 1,
  margin_top_mm: 22,
  margin_bottom_mm: 20,
  margin_left_mm: 28,
  margin_right_mm: 15,
  page_numbers: true,
  page_number_position: 'bottom',
  header_name: '',
  header_id: '',
  underline_headings: false,
  plain_headings: false,
  show_through: false,
  show_through_level: 'medium',
  pen_shadow: false,
  watermark: false,
  output: 'scanned',
  variation: 1,
  seed: 0,
};

// Same ranges as backend/layout/settings.py.
const RANGES = {
  font_size: [10, 28],
  line_spacing: [1.2, 3],
  paragraph_spacing: [0, 3, true],
  margin_top_mm: [5, 60],
  margin_bottom_mm: [5, 60],
  margin_left_mm: [5, 60],
  margin_right_mm: [5, 60],
  variation: [0, 2],
  seed: [0, 1000000, true],
};

/** Defaults for anything missing, numbers clamped to their allowed range,
 * header text trimmed to 80 characters, unknown keys dropped. */
export function cleanSettings(settings) {
  const out = {};
  for (const [k, def] of Object.entries(DEFAULT_SETTINGS)) {
    let v = settings?.[k];
    if (v === undefined || v === null || typeof v !== typeof def) v = def;
    if (RANGES[k]) {
      const [lo, hi, int] = RANGES[k];
      if (!Number.isFinite(v)) v = def;
      v = Math.min(hi, Math.max(lo, int ? Math.round(v) : v));
    }
    if (typeof v === 'string' && (k === 'header_name' || k === 'header_id')) v = v.slice(0, 80);
    out[k] = v;
  }
  return out;
}
