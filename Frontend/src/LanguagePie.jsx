import { useState } from "react";
import { maxShare, setShare, totalShare } from "./language-shares.js";

const colors = [
  "#f0b26d", "#81c6e0", "#eaa0af", "#9ec981", "#b9a9eb", "#66cdb4",
  "#ebcb75", "#e88978", "#88a6ed", "#c9a487", "#9fd1a8", "#c890ce",
];
const point = percent => {
  const angle = Math.PI * (percent / 50 - 0.5);
  return [50 + 48 * Math.cos(angle), 50 + 48 * Math.sin(angle)].join(" ");
};

function Slice({ color, start, share, active, onClick }) {
  const props = {
    fill: color,
    className: `pie-slice${active ? " active" : ""}${onClick ? " selectable" : ""}`,
    onClick,
  };
  if (share === 100) return <circle cx="50" cy="50" r="48" {...props} />;
  return <path d={`M 50 50 L ${point(start)} A 48 48 0 ${share > 50 ? 1 : 0} 1 ${point(start + share)} Z`} {...props} />;
}

export function LanguagePie({ options, shares, onChange }) {
  const [candidate, setCandidate] = useState("");
  const [selected, setSelected] = useState(null);
  const unassigned = 100 - totalShare(shares);
  const available = options.filter(name => !(name in shares));
  const remaining = Object.keys(shares).length < 30 ? available : [];
  const active = selected && selected in shares ? selected : null;

  let start = 0;
  const slices = Object.entries(shares).map(([name, share]) => {
    const slice = { name, share, start, color: colors[options.indexOf(name) % colors.length] };
    start += share;
    return slice;
  });
  if (unassigned > 0) slices.push({ name: "None", share: unassigned, start, color: "#304853" });

  function addLanguage() {
    if (!remaining.includes(candidate)) return;
    onChange(setShare(shares, candidate, 10));
    setSelected(candidate);
    setCandidate("");
  }

  function removeLanguage() {
    const next = { ...shares };
    delete next[active];
    onChange(next);
    setSelected(null);
  }

  return (
    <fieldset className="language-pie">
      <legend>Языки и их доли</legend>
      <div className="pie-layout">
        <svg className="pie-graphic" viewBox="0 0 100 100" aria-hidden="true">
          {slices.map(slice => (
            <Slice key={slice.name} {...slice} active={active === slice.name}
              onClick={slice.name === "None" ? undefined : () => setSelected(slice.name)} />
          ))}
        </svg>
        <ul className="pie-legend" aria-label="Доли языков">
          {slices.map(({ name, share, color }) => (
            <li key={name}>
              {name === "None" ? (
                <span className="pie-legend-row"><i style={{ background: color }} />{name}<b>{share}%</b></span>
              ) : (
                <button className="pie-legend-row" type="button" onClick={() => setSelected(name)} aria-pressed={active === name}>
                  <i style={{ background: color }} />{name}<b>{share}%</b>
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
      <div className="language-add">
        <select aria-label="Язык для добавления" value={candidate} disabled={!remaining.length}
          onChange={event => setCandidate(event.target.value)}>
          <option value="">Добавить язык…</option>
          {remaining.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
        <button type="button" aria-label="Добавить язык" disabled={!candidate} onClick={addLanguage}>+</button>
      </div>
      {active && (
        <div className="language-adjust">
          <div>
            <label htmlFor="language-share">Доля {active} · {shares[active]}%</label>
            <button type="button" onClick={removeLanguage} aria-label={`Удалить ${active}`}>Удалить</button>
          </div>
          <input id="language-share" type="range" min={1} max={maxShare(shares, active)} value={shares[active]}
            aria-valuetext={`${shares[active]}%`}
            onChange={event => onChange(setShare(shares, active, Number(event.target.value)))} />
        </div>
      )}
    </fieldset>
  );
}
