import { useEffect, useState } from 'react';
import { api } from '../services/api.js';

export const DEFAULT_SETTINGS = {
  style: 'neat',
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
  watermark: true,
  variation: 1,
  seed: 0,
};

function Num({ label, value, onChange, min, max, step = 1 }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input className="input" type="number" value={value} min={min} max={max} step={step} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

export default function SettingsPanel({ settings, onChange, compact = false }) {
  const [styles, setStyles] = useState([]);
  useEffect(() => {
    api.styles().then(setStyles).catch(() => setStyles([]));
  }, []);
  const set = (k) => (v) => onChange({ ...settings, [k]: v });
  return (
    <div className={compact ? 'grid-3' : 'grid-3'} data-testid="render-settings">
      <label className="field">
        <span>Handwriting style</span>
        <select className="select" value={settings.style} onChange={(e) => set('style')(e.target.value)}>
          {(styles.length ? styles : [{ id: settings.style, label: settings.style }]).map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Ink</span>
        <select className="select" value={settings.ink} onChange={(e) => set('ink')(e.target.value)}>
          <option value="blue">Blue</option>
          <option value="black">Black</option>
        </select>
      </label>
      <label className="field">
        <span>Paper</span>
        <select className="select" value={settings.paper} onChange={(e) => set('paper')(e.target.value)}>
          <option value="ruled">Ruled</option>
          <option value="blank">Blank</option>
          <option value="grid">Grid</option>
        </select>
      </label>
      <label className="field">
        <span>Page size</span>
        <select className="select" value={settings.page_size} onChange={(e) => set('page_size')(e.target.value)}>
          <option value="A4">A4</option>
          <option value="Letter">US Letter</option>
        </select>
      </label>
      <Num label="Font size (pt)" value={settings.font_size} min={10} max={28} onChange={set('font_size')} />
      <Num label="Line spacing" value={settings.line_spacing} min={1.2} max={3} step={0.1} onChange={set('line_spacing')} />
      <Num label="Space after paragraphs (lines)" value={settings.paragraph_spacing} min={0} max={3} onChange={set('paragraph_spacing')} />
      <Num label="Handwriting variation" value={settings.variation} min={0} max={2} step={0.1} onChange={set('variation')} />
      {!compact && (
        <>
          <Num label="Top margin (mm)" value={settings.margin_top_mm} min={5} max={60} onChange={set('margin_top_mm')} />
          <Num label="Bottom margin (mm)" value={settings.margin_bottom_mm} min={5} max={60} onChange={set('margin_bottom_mm')} />
          <Num label="Left margin (mm)" value={settings.margin_left_mm} min={5} max={60} onChange={set('margin_left_mm')} />
          <Num label="Right margin (mm)" value={settings.margin_right_mm} min={5} max={60} onChange={set('margin_right_mm')} />
          <Num label="Variation seed" value={settings.seed} min={0} max={1000000} onChange={set('seed')} />
        </>
      )}
      <label className="field">
        <span>Page numbers</span>
        <select className="select" value={settings.page_numbers ? 'yes' : 'no'} onChange={(e) => set('page_numbers')(e.target.value === 'yes')}>
          <option value="yes">Show</option>
          <option value="no">Hide</option>
        </select>
      </label>
      <label className="field">
        <span>“Generated with WriteAI” footer</span>
        <select className="select" value={settings.watermark ? 'yes' : 'no'} onChange={(e) => set('watermark')(e.target.value === 'yes')}>
          <option value="yes">Show (recommended)</option>
          <option value="no">Hide</option>
        </select>
      </label>
    </div>
  );
}
