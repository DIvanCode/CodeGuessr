import { useEffect, useRef, useState } from "react";

const BASE = { x: 0, y: 65, width: 1000, height: 700 };
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const polygonPoints = polygon => polygon.map(point => point.join(",")).join(" ");
const shades = ["#f9f0dd 13%", "#0e252d 14%", "#f9f0dd 29%", "#0e252d 5%", "#0e252d 26%"];

function moveView(view) {
  return {
    ...view,
    x: clamp(view.x, -45, BASE.width - view.width + 45),
    y: clamp(view.y, BASE.y - 45, BASE.y + BASE.height - view.height + 45),
  };
}

function zoomed(view, factor, origin = { x: view.x + view.width / 2, y: view.y + view.height / 2 }) {
  const width = clamp(view.width / factor, BASE.width / 5, BASE.width);
  const ratio = width / view.width;
  return moveView({
    width,
    height: view.height * ratio,
    x: origin.x + (view.x - origin.x) * ratio,
    y: origin.y + (view.y - origin.y) * ratio,
  });
}

function mapPoint(svg, event) {
  return new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
}

function Marker({ point, correct = false }) {
  if (!point) return null;
  return (
    <g className={correct ? "answer-marker" : "guess-marker"} transform={`translate(${point.x} ${point.y})`}>
      <path d="M 0 0 C -2 -4 -11 -11 -11 -19 A 11 11 0 0 1 11 -19 C 11 -11 2 -4 0 0 Z" />
      <circle cy="-19" r="3" fill="#14292e" stroke="none" />
    </g>
  );
}

export function Atlas({ data, byLanguage, enabled, selected, pin, result, hint, onChoose }) {
  const svg = useRef(null);
  const drag = useRef(null);
  const [view, setView] = useState(BASE);
  const [dragging, setDragging] = useState(false);
  const [tooltip, setTooltip] = useState(null);
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const zoom = BASE.width / view.width;
  const guess = result ? result.pin : pin;
  const answer = result?.answer;
  const guessedCountry = result?.selected_repository_id ?? selected;
  const hintRegion = data.regions.find(region => region.id === hint);
  const searchText = query.trim().toLowerCase();
  const matches = searchText ? data.repositories.filter(repo => repo.name.toLowerCase().includes(searchText))
    .sort((a, b) => Number(b.name.toLowerCase().endsWith(`/${searchText}`)) -
      Number(a.name.toLowerCase().endsWith(`/${searchText}`)) || a.name.localeCompare(b.name)).slice(0, 8) : [];

  useEffect(() => {
    const element = svg.current;
    function wheel(event) {
      event.preventDefault();
      const point = mapPoint(element, event);
      setView(previous => zoomed(previous, event.deltaY < 0 ? 1.2 : 1 / 1.2, point));
      setTooltip(null);
    }
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);

  useEffect(() => {
    if (result) setView(BASE);
  }, [result]);

  function choose(repo, point = repo, name = repo?.name ?? "") {
    onChoose(name, point ? { x: point.x, y: point.y } : null, repo?.id ?? null);
    setQuery("");
    setTooltip(null);
    setShowSearch(false);
  }

  function chooseFromSearch(repo) {
    if (repo) {
      choose(repo);
      setView(previous => moveView({
        ...previous,
        x: repo.x - previous.width / 2,
        y: repo.y - previous.height / 2,
      }));
    } else if (searchText) {
      choose(null, null, query.trim());
    }
  }

  function pointerDown(event) {
    if (event.button !== 0 || !event.isPrimary) return;
    const element = event.currentTarget;
    const country = data.repositories.find(repo => repo.id === Number(event.target.dataset.repo));
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      view,
      scale: element.getScreenCTM().a,
      point: mapPoint(element, event),
      country,
      moved: false,
    };
    element.setPointerCapture(event.pointerId);
    setShowSearch(false);
    setTooltip(null);
  }

  function pointerMove(event) {
    const current = drag.current;
    if (current) {
      const dx = event.clientX - current.x;
      const dy = event.clientY - current.y;
      current.moved ||= Math.hypot(dx, dy) > 5;
      if (current.moved) {
        setDragging(true);
        setView(moveView({ ...current.view, x: current.view.x - dx / current.scale, y: current.view.y - dy / current.scale }));
      }
      return;
    }
    const repo = data.repositories.find(item => item.id === Number(event.target.dataset.repo));
    const box = event.currentTarget.getBoundingClientRect();
    setTooltip(repo ? {
      repo,
      x: clamp(event.clientX - box.left + 12, 8, box.width - 218),
      y: clamp(event.clientY - box.top + 12, 8, box.height - 58),
    } : null);
  }

  function endDrag() {
    drag.current = null;
    setDragging(false);
  }

  function pointerUp() {
    const current = drag.current;
    endDrag();
    if (!current || current.moved || !enabled) return;
    const { x, y } = current.point;
    if (current.country) choose(current.country);
    else if (x >= 0 && x <= 1000 && y >= 0 && y <= 800) choose(null, { x: Math.round(x), y: Math.round(y) });
  }

  return (
    <section className="atlas" aria-label="Карта репозиториев GitHub">
      <div className="map-wrap">
        <svg
          ref={svg} id="map" className={dragging ? "dragging" : ""} role="img"
          viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
          aria-label={`${byLanguage ? "Материки по основному языку" : "Шесть тематических материков"}. Каждая страна — один репозиторий.`}
          onPointerDown={pointerDown} onPointerMove={pointerMove}
          onPointerUp={pointerUp} onPointerCancel={endDrag} onPointerLeave={() => setTooltip(null)}
        >
          <defs>
            <pattern id="sea-grid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path d="M 48 0 H 0 V 48" fill="none" stroke="#78949c" strokeOpacity=".13" />
            </pattern>
          </defs>
          <rect x="-1000" y="-1000" width="3000" height="3000" fill="url(#sea-grid)" />
          {data.regions.map(region => (
            <g key={region.id} className={hint && hint !== region.id ? "continent dim" : "continent"} style={{ "--land": region.color }}>
              <polygon points={polygonPoints(region.outline)} className="continental-shelf" />
              <polygon points={polygonPoints(region.outline)} className="coastline" />
              {data.repositories.filter(repo => repo.region === region.id).map(repo => (
                <polygon
                  key={repo.id} data-repo={repo.id} points={polygonPoints(repo.polygon)}
                  style={{ "--shade": shades[(repo.id * 13 + Math.floor(repo.id / 5)) % shades.length] }}
                  className={`country${guessedCountry === repo.id ? " selected" : ""}${answer?.repository_id === repo.id ? " correct" : ""}`}
                />
              ))}
              {zoom < 1.65 && <text x={region.x} y={region.y} className="island-label">{region.name}</text>}
            </g>
          ))}
          {zoom >= 1.65 && data.repositories
            .filter(repo => zoom >= 2.4 || repo.size_mb >= 30)
            .map(repo => <text key={repo.id} x={repo.x} y={repo.y} className="country-label">{repo.name.split("/").at(-1)}</text>)}
          {guess && answer && <line className="answer-line" x1={guess.x} y1={guess.y} x2={answer.x} y2={answer.y} />}
          <Marker point={guess} />
          <Marker point={answer} correct />
        </svg>

        <div className="search" onBlur={event => {
          if (!event.currentTarget.contains(event.relatedTarget)) setShowSearch(false);
        }}>
          <label className="search-box">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" />
            </svg>
            <input type="search" maxLength={200} autoComplete="off" value={query}
              placeholder="Найти репозиторий…" aria-label="Поиск репозитория" aria-controls="search-results" disabled={!enabled}
              onFocus={() => setShowSearch(true)} onChange={event => { setQuery(event.target.value); setShowSearch(true); }}
              onKeyDown={event => {
                if (event.key === "Escape") setShowSearch(false);
                if (event.key === "Enter" && showSearch && searchText) chooseFromSearch(matches[0]);
              }}
            />
          </label>
          {enabled && showSearch && searchText && (
            <div id="search-results" className="search-results">
              {matches.length ? matches.map(repo => (
                <button key={repo.id} type="button" onClick={() => chooseFromSearch(repo)}>
                  {repo.name}<small>≈ {repo.size_mb} МБ</small>
                </button>
              )) : <button type="button" onClick={() => chooseFromSearch()}>Указать «{query.trim()}»</button>}
            </div>
          )}
        </div>
        <div className="zoom" aria-label="Масштаб карты">
          <button type="button" aria-label="Приблизить" onClick={() => setView(value => zoomed(value, 1.4))}>+</button>
          <button type="button" aria-label="Отдалить" onClick={() => setView(value => zoomed(value, 1 / 1.4))}>−</button>
          <button type="button" aria-label="Показать всю карту" onClick={() => setView(BASE)}>↗</button>
        </div>
        {tooltip && (
          <div className="map-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
            <strong>{tooltip.repo.name}</strong><br /><span>≈ {tooltip.repo.size_mb} МБ</span>
          </div>
        )}
        {hintRegion && !result && <div className="map-region">{hintRegion.name}</div>}
      </div>
      <footer className="legend">
        <span><b>Материк</b> — {byLanguage ? "основной язык" : "тематика проекта"}</span>
        <span><b>Страна</b> — его репозиторий</span>
        <span><b>Клик</b> выбирает страну, а <b>колесо</b> меняет масштаб</span>
      </footer>
    </section>
  );
}
