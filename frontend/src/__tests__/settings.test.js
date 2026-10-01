import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS, cleanSettings } from '../preview/settings.js';
import { errorText } from '../components/ui.jsx';

describe('cleanSettings (what Update Preview / Generate Final PDF send)', () => {
  it('fills missing fields from defaults and drops unknown ones', () => {
    const s = cleanSettings({ style: 'student', made_up: 1 });
    expect(s.style).toBe('student');
    expect(s).not.toHaveProperty('made_up');
    expect(Object.keys(s).sort()).toEqual(Object.keys(DEFAULT_SETTINGS).sort());
  });

  it('never sends an out-of-range or empty number', () => {
    const s = cleanSettings({ font_size: 0, line_spacing: 9, margin_left_mm: NaN, paragraph_spacing: 1.6, seed: -5 });
    expect(s.font_size).toBe(10);
    expect(s.line_spacing).toBe(3);
    expect(s.margin_left_mm).toBe(DEFAULT_SETTINGS.margin_left_mm);
    expect(s.paragraph_spacing).toBe(2);
    expect(s.seed).toBe(0);
  });

  it('keeps valid values and limits header text', () => {
    const s = cleanSettings({ font_size: 17, header_name: 'x'.repeat(100), pen_shadow: true });
    expect(s.font_size).toBe(17);
    expect(s.header_name).toHaveLength(80);
    expect(s.pen_shadow).toBe(true);
  });
});

describe('errorText', () => {
  it('names the field instead of "The request is invalid."', () => {
    const e = { code: 'VALIDATION_ERROR', message: 'The request is invalid.', details: { errors: [{ loc: 'body.settings.margin_left_mm', msg: 'Input should be greater than or equal to 5' }] } };
    expect(errorText(e)).toBe('Please check: margin left (mm) – Input should be greater than or equal to 5');
  });

  it('explains an out-of-date server', () => {
    const e = { code: 'VALIDATION_ERROR', details: { errors: [{ loc: 'body.settings.pen_shadow', msg: 'Extra inputs are not permitted' }] } };
    expect(errorText(e)).toMatch(/older than the website/);
  });
});
