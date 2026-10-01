import { useEffect, useState } from 'react';
import { api } from '../services/api.js';

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
  watermark: false,
  output: 'scanned',
  variation: 1,
  seed: 0,
};

/**
 * "Assignment sheet": loose unruled paper with a header line and margin line,
 * name + ID top-left, page number top-right, hand-underlined headings and
 * faint writing showing through from the back, like a real submitted
 * assignment. Keeps the user's name/ID and everything not listed here.
 */
export const ASSIGNMENT_PRESET = {
  paper: 'assignment',
  style: 'student',
  ink: 'ballpoint',
  output: 'photo',
  page_numbers: true,
  page_number_position: 'top-right',
  underline_headings: true,
  plain_headings: true,
  show_through: true,
  font_size: 17,
  line_spacing: 1.5,
  paragraph_spacing: 0,
  margin_left_mm: 20,
  margin_right_mm: 8,
  margin_bottom_mm: 10,
};

function YesNo({ label, value, onChange, testid }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select className="select" value={value ? 'yes' : 'no'} onChange={(e) => onChange(e.target.value === 'yes')} data-testid={testid}>
        <option value="no">Off</option>
        <option value="yes">On</option>
      </select>
    </label>
  );
}

function Text({ label, value, onChange, placeholder, testid }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input className="input" type="text" maxLength={80} value={value ?? ''} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </label>
  );
}

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
  const isAssignment = settings.paper === 'assignment' && settings.underline_headings && settings.page_number_position === 'top-right';
  return (
    <div className="stack" data-testid="render-settings">
    <div className="row">
      <button type="button" className={`btn ${isAssignment ? 'btn-primary' : ''}`} onClick={() => onChange({ ...settings, ...ASSIGNMENT_PRESET })} data-testid="preset-assignment">
        📝 Handwritten assignment (real-photo look)
      </button>
      <button type="button" className="btn" onClick={() => onChange({ ...DEFAULT_SETTINGS, header_name: settings.header_name, header_id: settings.header_id })} data-testid="preset-notes">
        📒 Notebook notes
      </button>
      <span className="small muted">Presets: one click sets the paper, style and page layout; adjust anything after.</span>
    </div>
    <div className="grid-3">
      <label className="field">
        <span>Handwriting style</span>
        <select className="select" value={settings.style} onChange={(e) => set('style')(e.target.value)}>
          {(styles.length ? styles : [{ id: settings.style, label: settings.style }]).map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Look</span>
        <select className="select" value={settings.output} onChange={(e) => set('output')(e.target.value)} data-testid="output-look">
          <option value="photo">Photo of handwritten pages (most realistic)</option>
          <option value="scanned">Scanned handwritten page</option>
          <option value="clean">Clean digital page</option>
        </select>
      </label>
      <label className="field">
        <span>Ink</span>
        <select className="select" value={settings.ink} onChange={(e) => set('ink')(e.target.value)}>
          <option value="blue">Blue</option>
          <option value="ballpoint">Blue ballpoint (bright)</option>
          <option value="black">Black</option>
        </select>
      </label>
      <label className="field">
        <span>Paper</span>
        <select className="select" value={settings.paper} onChange={(e) => set('paper')(e.target.value)}>
          <option value="ruled">Ruled</option>
          <option value="blank">Blank</option>
          <option value="grid">Grid</option>
          <option value="assignment">Assignment sheet (unruled)</option>
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
      <Text label="Header: name (top-left of every page)" value={settings.header_name} onChange={set('header_name')} placeholder="e.g. your name" testid="header-name" />
      <Text label="Header: roll / ID number" value={settings.header_id} onChange={set('header_id')} placeholder="e.g. roll number" testid="header-id" />
      <label className="field">
        <span>Page numbers</span>
        <select
          className="select"
          value={settings.page_numbers ? settings.page_number_position || 'bottom' : 'none'}
          onChange={(e) => onChange({ ...settings, page_numbers: e.target.value !== 'none', page_number_position: e.target.value === 'none' ? settings.page_number_position : e.target.value })}
          data-testid="page-numbers"
        >
          <option value="bottom">Bottom centre</option>
          <option value="top-right">Top right</option>
          <option value="none">Hide</option>
        </select>
      </label>
      <YesNo label="Underline headings (hand-drawn)" value={settings.underline_headings} onChange={set('underline_headings')} testid="underline-headings" />
      <YesNo label="Headings written like normal text (not bold/large)" value={settings.plain_headings} onChange={set('plain_headings')} testid="plain-headings" />
      <YesNo label="Show-through from back of page (scan/photo look)" value={settings.show_through} onChange={set('show_through')} testid="show-through" />
      <label className="field">
        <span>“Generated with WriteAI” footer</span>
        <select className="select" value={settings.watermark ? 'yes' : 'no'} onChange={(e) => set('watermark')(e.target.value === 'yes')}>
          <option value="no">Hide</option>
          <option value="yes">Show</option>
        </select>
      </label>
    </div>
    </div>
  );
}
