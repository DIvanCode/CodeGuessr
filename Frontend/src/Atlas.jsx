import { useEffect, useRef, useState } from "react";

const BASE = { x: 0, y: 65, width: 1000, height: 700 };
const LABEL_SIZE = 13;
const ISLAND_LABEL_SIZE = 19;
const MIN_LABEL_WIDTH = 42;
const FOLDERS_PER_REPOSITORY = 7;
const FOLDER_REQUESTS = 4;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const polygonPoints = polygon => polygon.map(point => point.join(",")).join(" ");
const shades = ["#f9f0dd 13%", "#0e252d 14%", "#f9f0dd 29%", "#0e252d 5%", "#0e252d 26%"];
const LEVEL_TITLES = { region: "Материки", group: "Группы", repository: "Репозитории", folder: "Папки" };
const SIMILAR_PROJECTS ="похожие проекты по описанию и topics";
const AXES = {
  demo: { label: "Шесть тематических материков", region: "тематика проекта", group: "семейство языков" },
  topic: { label: "Материки из похожих по описанию проектов", region: SIMILAR_PROJECTS, group: "основной язык" },
  language: { label: "Материки по основному языку проектов", region: "основной язык", group: SIMILAR_PROJECTS },
};
const shadeOf = index => shades[(index * 13 + Math.floor(index / 5)) % shades.length];

export const LEVELS = {
  easy: ["region", "repository"],
  medium: ["region", "group", "repository"],
  hard: ["region", "group", "repository", "folder"],
};

function polygonArea(polygon) {
  let sum = 0;
  polygon.forEach(([x1, y1], index) => {
    const [x2, y2] = polygon[(index + 1) % polygon.length];
    sum += x1 * y2 - x2 * y1;
  });
  return Math.abs(sum) / 2;
}

function contains(polygon, { x, y }) {
  let inside = false;
  polygon.forEach(([x1, y1], index) => {
    const [x2, y2] = polygon[(index + 1) % polygon.length];
    if ((y1 > y) !== (y2 > y) && x < x1 + (y - y1) * (x2 - x1) / (y2 - y1)) inside = !inside;
  });
  return inside;
}

function thresholds(data, levels) {
  const land = data.regions.reduce((sum, region) => sum + polygonArea(region.outline), 0);
  const counts = {
    region: data.regions.length, group: data.groups.length, repository: data.repositories.length,
    folder: data.repositories.length * FOLDERS_PER_REPOSITORY,
  };
  let previous = 0;
  return levels.map((level, index) => {
    if (index === 0) return 0;
    previous = Math.max(index === 1 ? 1.4 : previous * 1.5, 90 / Math.sqrt(land / Math.max(1, counts[level])));
    return previous;
  });
}

function folderName(id) {
  return id === "*" ? "(корень)" : id.endsWith("/*") ? `${id.slice(0, -1)}(файлы)` : id;
}

export function locate(data, folders, point, levels, depth) {
  const found = {};
  const visible = level => levels.indexOf(level) !== -1 && levels.indexOf(level) <= depth;
  found.region = data.regions.find(region => contains(region.outline, point));
  if (visible("group")) found.group = data.groups.find(group => contains(group.polygon, point));
  if (visible("repository")) found.repository = data.repositories.find(repo => contains(repo.polygon, point));
  if (visible("folder") && found.repository && Array.isArray(folders[found.repository.id])) {
    found.folder = folders[found.repository.id].find(folder => contains(folder.polygon, point));
  }
  return found;
}

export function describe(location) {
  return [
    location.region?.name, location.group?.name, location.repository?.name,
    location.folder && folderName(location.folder.id),
  ].filter(Boolean).join(" › ");
}

export function describeIds(data, ids) {
  return describe({
    region: data.regions.find(region => region.id === ids.region),
    group: data.groups.find(group => group.id === ids.group),
    repository: data.repositories.find(repo => repo.id === ids.repository),
    folder: ids.folder ? { id: ids.folder } : undefined,
  });
}

function moveView(view) {
  return {
    ...view,
    x: clamp(view.x, -45, BASE.width - view.width + 45),
    y: clamp(view.y, BASE.y - 45, BASE.y + BASE.height - view.height + 45),
  };
}

function zoomed(view, factor, maxZoom, origin = { x: view.x + view.width / 2, y: view.y + view.height / 2 }) {
  const width = clamp(view.width / factor, BASE.width / maxZoom, BASE.width);
  const ratio = width / view.width;
  return moveView({
    width,
    height: view.height * ratio,
    x: origin.x + (view.x - origin.x) * ratio,
    y: origin.y + (view.y - origin.y) * ratio,
  });
}

function fitted(points, maxZoom) {
  const xs = points.map(point => point.x);
  const ys = points.map(point => point.y);
  const ratio = BASE.height / BASE.width;
  const width = clamp(Math.max((Math.max(...xs) - Math.min(...xs)) * 1.6, (Math.max(...ys) - Math.min(...ys)) * 1.6 / ratio),
    BASE.width / maxZoom * 4, BASE.width);
  const centerX = (Math.max(...xs) + Math.min(...xs)) / 2;
  const centerY = (Math.max(...ys) + Math.min(...ys)) / 2;
  return moveView({ width, height: width * ratio, x: centerX - width / 2, y: centerY - width * ratio / 2 });
}

function mapPoint(svg, event) {
  return new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
}

function Marker({ point, zoom, correct = false }) {
  if (!point) return null;
  return (
    <g className={correct ? "answer-marker" : "guess-marker"} transform={`translate(${point.x} ${point.y}) scale(${1 / Math.sqrt(zoom)})`}>
      <path d="M 0 0 C -2 -4 -11 -11 -11 -19 A 11 11 0 0 1 11 -19 C 11 -11 2 -4 0 0 Z" />
      <circle cy="-19" r="3" fill="#14292e" stroke="none" />
    </g>
  );
}

function inView(view, item) {
  return item.x >= view.x && item.x <= view.x + view.width && item.y >= view.y && item.y <= view.y + view.height;
}

export function Atlas({ data, difficulty, folders, onNeedFolders, ownerMap, enabled, choice, pin, result, hint, onChoose, children }) {
  const svg = useRef(null);
  const drag = useRef(null);
  const touches = useRef(new Map());
  const pinch = useRef(null);
  const axes = AXES[ownerMap ? data.region_axis ?? "topic" : "demo"];
  const levels = LEVELS[difficulty] ?? LEVELS.easy;
  const steps = thresholds(data, levels);
  const maxZoom = Math.max(5, steps.at(-1) * 3);
  const maxZoomRef = useRef(maxZoom);
  maxZoomRef.current = maxZoom;
  const [view, setView] = useState(BASE);
  const [dragging, setDragging] = useState(false);
  const [tooltip, setTooltip] = useState(null);
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const zoom =BASE.width / view.width;
  const depth = steps.reduce((deepest, step, index) => (zoom >= step ? index : deepest), 0);
  const choiceDepth = difficulty === "easy" ? levels.length - 1 : depth;
  const visibleLevel = level => levels.includes(level) && levels.indexOf(level) <= choiceDepth;
  const repositoryIndex = levels.indexOf("repository");
  const folderIndex = levels.indexOf("folder");
  const guess = result ? result.pin : pin;
  const answer = result?.answer;
  const guessedCountry = result ? result.location.repository : choice?.level === "repository" ? choice.id : null;
  const guessedFolder = result ? { repo: result.location.repository, id: result.location.folder }
    : choice?.level === "folder" ? { repo: choice.repository, id: choice.id } : null;
  const guessedGroup = result ? result.location.group : choice?.level === "group" ? choice.id : null;
  const guessedRegion = choice?.level === "region" ? choice.id : null;
  const hintRegion = data.regions.find(region => region.id === hint);
  const searchText = query.trim().toLowerCase();
  const matches = searchText ? data.repositories.filter(repo => repo.name.toLowerCase().includes(searchText))
    .sort((a, b) => Number(b.name.toLowerCase().endsWith(`/${searchText}`)) -
      Number(a.name.toLowerCase().endsWith(`/${searchText}`)) || a.name.localeCompare(b.name)).slice(0, 8) : [];
  const shownFolders = folderIndex !== -1 && depth >= folderIndex
    ? data.repositories.filter(repo => Array.isArray(folders[repo.id]) && inView(view, repo))
      .flatMap(repo => folders[repo.id].map(folder => ({ ...folder, repo: repo.id })))
    : [];

  useEffect(() => {
    const element = svg.current;
    function wheel(event) {
      event.preventDefault();
      const point = mapPoint(element, event);
      setView(previous => zoomed(previous, event.deltaY < 0 ? 1.2 : 1 / 1.2, maxZoomRef.current, point));
      setTooltip(null);
    }
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);

  useEffect(() => { setPanelOpen(true); }, [choice, pin]);

  useEffect(() => {
    if (!result) return;
    const points = [result.pin, result.answer].filter(Boolean);
    setView(result.answer.folder ? fitted(points, maxZoomRef.current) : BASE);
  }, [result]);

  useEffect(() => {
    if (folderIndex === -1 || zoom < steps[folderIndex] * 0.6) return undefined;
    const timer = setTimeout(() => {
      const middle = { x: view.x + view.width / 2, y: view.y + view.height / 2 };
      const wanted = data.repositories.filter(repo => inView(view, repo) && !(repo.id in folders))
        .sort((a, b) => Math.hypot(a.x - middle.x, a.y - middle.y) - Math.hypot(b.x - middle.x, b.y - middle.y))
        .slice(0, FOLDER_REQUESTS).map(repo => repo.id);
      if (wanted.length) onNeedFolders(wanted);
    }, 250);
    return () => clearTimeout(timer);
  }, [view, folders, data]);

  function choose(location, point, chosenDepth) {
    const level = levels[chosenDepth];
    const item = location[level];
    onChoose({
      repository: location.repository?.name ?? "",
      label: describe(location),
      pin: point ? { x: point.x, y: point.y } : null,
      choice: item ? { level, id: item.id, repository: location.repository?.id } : null,
      depth: chosenDepth,
    });
    setQuery("");
    setTooltip(null);
    setShowSearch(false);
  }

  function chooseFromSearch(repo) {
    if (repo) {
      const location = {
        region: data.regions.find(region => region.id === repo.region),
        group: data.groups.find(group => group.id === repo.group),
        repository: repo,
      };
      choose(location, repo, repositoryIndex);
      const width = Math.min(view.width, BASE.width / Math.max(1, steps[repositoryIndex] * 1.2));
      setView(moveView({ width, height: width * BASE.height / BASE.width, x: repo.x - width / 2, y: repo.y - width * BASE.height / BASE.width / 2 }));
    } else if (searchText) {
      onChoose({ repository: query.trim(), label: query.trim(), pin: null, choice: null, depth: repositoryIndex });
      setQuery("");
      setShowSearch(false);
    }
  }

  function startPinch(element) {
    const [first, second] = [...touches.current.values()];
    const middle = { clientX: (first.x + second.x) / 2, clientY: (first.y + second.y) / 2 };
    pinch.current = {
      distance: Math.hypot(first.x - second.x, first.y - second.y) || 1,
      middle,
      origin: mapPoint(element, middle),
      scale: element.getScreenCTM().a,
      view,
    };
    drag.current = null;
    setDragging(false);
  }

  function movePinch() {
    const [first, second] = [...touches.current.values()];
    const start = pinch.current;
    const factor = Math.hypot(first.x - second.x, first.y - second.y) / start.distance;
    const next = zoomed(start.view, factor, maxZoomRef.current, start.origin);
    const scale = start.scale * start.view.width / next.width;
    const dx = (first.x + second.x) / 2 - start.middle.clientX;
    const dy = (first.y + second.y) / 2 - start.middle.clientY;
    setView(moveView({ ...next, x: next.x - dx / scale, y: next.y - dy / scale }));
  }

  function releasePointer(event) {
    touches.current.delete(event.pointerId);
    if (pinch.current && touches.current.size < 2) {
      pinch.current = null;
      drag.current = null;
      return true;
    }
    return false;
  }

  function pointerDown(event) {
    const element = event.currentTarget;
    if (event.pointerType !== "mouse") {
      touches.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      element.setPointerCapture(event.pointerId);
      if (touches.current.size === 2) {
        startPinch(element);
        return;
      }
    }
    if (event.button !== 0 || !event.isPrimary) return;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      view,
      scale: element.getScreenCTM().a,
      point: mapPoint(element, event),
      moved: false,
    };
    element.setPointerCapture(event.pointerId);
    setShowSearch(false);
    setTooltip(null);
  }

  function deepestDepth(location) {
    return levels.reduce((deepest, level, index) => (location[level] ? index : deepest), -1);
  }

  function pointerMove(event) {
    if (touches.current.has(event.pointerId)) {
      touches.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pinch.current) {
        movePinch();
        return;
      }
    }
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
    if (event.pointerType !== "mouse") return;
    const location = locate(data, folders, mapPoint(event.currentTarget, event), levels, choiceDepth);
    const box = event.currentTarget.getBoundingClientRect();
    setTooltip(location.region ? {
      text: describe(location),
      size: location.repository?.size_mb,
      x: clamp(event.clientX - box.left + 12, 8, box.width - 218),
      y: clamp(event.clientY - box.top + 12, 8, box.height - 58),
    } : null);
  }

  function endDrag(event) {
    releasePointer(event);
    drag.current = null;
    setDragging(false);
  }

  function pointerUp(event) {
    if (releasePointer(event)) return;
    const current = drag.current;
    drag.current = null;
    setDragging(false);
    if (!current || current.moved || !enabled) return;
    const { x, y } = current.point;
    const location = locate(data, folders, current.point, levels, choiceDepth);
    const found = deepestDepth(location);
    if (found >= 0) choose(location, location[levels[found]], found);
    else if (x >= 0 && x <= 1000 && y >= 0 && y <= 800) choose({}, { x: Math.round(x), y: Math.round(y) }, 0);
  }

  const labelStyle = size => ({ fontSize: size / zoom, strokeWidth: 3 / zoom });
  const labelFits = polygon => Math.sqrt(polygonArea(polygon)) * zoom >= MIN_LABEL_WIDTH;
  const repositoriesShown = visibleLevel("repository");
  const labelLevel = levels[depth];
  const foldersShownFor = new Set(shownFolders.map(folder => folder.repo));
  const labels = [];
  if (labelLevel === "group") {
    data.groups.filter(group => inView(view, group) && labelFits(group.polygon))
      .forEach(group => labels.push({ key: `g${group.id}`, x: group.x, y: group.y, text: group.name }));
  }
  if (labelLevel === "repository" || labelLevel === "folder") {
    data.repositories.filter(repo => inView(view, repo) && !foldersShownFor.has(repo.id) && labelFits(repo.polygon))
      .forEach(repo => labels.push({ key: `r${repo.id}`, x: repo.x, y: repo.y, text: repo.name.split("/").at(-1) }));
  }
  shownFolders.filter(folder => labelFits(folder.polygon))
    .forEach(folder => labels.push({ key: `f${folder.repo}:${folder.id}`, x: folder.x, y: folder.y, text: folderName(folder.id) }));

  return (
    <section className="atlas" aria-label="Карта репозиториев GitHub">
      <div className="map-area">
        <div className="map-wrap">
          <svg
            ref={svg} id="map" className={dragging ? "dragging" : ""} role="img"
            viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
            aria-label={`${axes.label}. Каждая страна — один репозиторий.`}
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
                <polygon points={polygonPoints(region.outline)} className={`coastline${guessedRegion === region.id ? " selected" : ""}`} />
                {data.groups.filter(group => group.region === region.id).map((group, index) => (
                  <polygon key={group.id} points={polygonPoints(group.polygon)} style={{ "--shade": shadeOf(index) }}
                    className={`group${repositoriesShown ? " behind" : ""}${guessedGroup === group.id ? " selected" : ""}`} />
                ))}
                {data.repositories.filter(repo => repo.region === region.id).map(repo => (
                  <polygon
                    key={repo.id} points={polygonPoints(repo.polygon)} style={{ "--shade": shadeOf(repo.id) }}
                    className={`country${repositoriesShown ? "" : " concealed"}${guessedCountry === repo.id ? " selected" : ""}${answer?.repository_id === repo.id ? " correct" : ""}`}
                  />
                ))}
              </g>
            ))}
            {shownFolders.map((folder, index) => {
              const region = data.regions.find(item => item.id === data.repositories.find(repo => repo.id === folder.repo).region);
              const selected = guessedFolder?.repo === folder.repo && guessedFolder.id === folder.id;
              const correct = answer?.repository_id === folder.repo && answer?.folder === folder.id;
              return (
                <polygon key={`${folder.repo}:${folder.id}`} points={polygonPoints(folder.polygon)}
                  style={{ "--land": region.color, "--shade": shadeOf(index + 2) }}
                  className={`folder${selected ? " selected" : ""}${correct ? " correct" : ""}`} />
              );
            })}
            {answer?.folder_polygon && <polygon points={polygonPoints(answer.folder_polygon)} className="folder answer-area" />}
            {depth === 0 && data.regions.map(region => (
              <text key={region.id} x={region.x} y={region.y} className="island-label" style={labelStyle(ISLAND_LABEL_SIZE)}>{region.name}</text>
            ))}
            {labels.map(label => <text key={label.key} x={label.x} y={label.y} className="country-label" style={labelStyle(LABEL_SIZE)}>{label.text}</text>)}
            {guess && answer && <line className="answer-line" x1={guess.x} y1={guess.y} x2={answer.x} y2={answer.y} />}
            <Marker point={guess} zoom={zoom} />
            <Marker point={answer} zoom={zoom} correct />
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
            <button type="button" aria-label="Приблизить" onClick={() => setView(value => zoomed(value, 1.4, maxZoom))}>+</button>
            <button type="button" aria-label="Отдалить" onClick={() => setView(value => zoomed(value, 1 / 1.4, maxZoom))}>−</button>
            <button type="button" aria-label="Показать всю карту" onClick={() => setView(BASE)}>↗</button>
          </div>
          {tooltip && (
            <div className="map-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
              <strong>{tooltip.text}</strong>
              {tooltip.size !== undefined && <><br /><span>≈ {tooltip.size} МБ</span></>}
            </div>
          )}
          <div className="map-status">
            {levels.length > 2 && <span className="map-depth">{LEVEL_TITLES[levels[depth]]} · ×{zoom.toFixed(1)}</span>}
            {hintRegion && !result && <span className="map-region">{hintRegion.name}</span>}
          </div>
        </div>
        {children && (
          <div className={`answer-panel${panelOpen ? "" : " collapsed"}`} aria-label="Ответ">
            <button type="button" className="panel-toggle" aria-expanded={panelOpen} onClick={() => setPanelOpen(open => !open)}>
              {panelOpen ? "Свернуть ▾" : result ? "Результат раунда ▴" : "Развернуть ▴"}
            </button>
            <div className="panel-body">{children}</div>
          </div>
        )}
      </div>
      <footer className="legend">
        <span><b>Материк</b> — {axes.region}</span>
        {levels.includes("group") && <span><b>Группа</b> — {axes.group}</span>}
        <span><b>Страна</b> — репозиторий</span>
        {levels.includes("folder") && <span><b>Город</b> — папка внутри репозитория</span>}
        <span><b className="only-mouse">Колесо</b><b className="only-touch">Щипок</b> приближает: глубже видны {levels.length > 2 ? "новые границы" : "названия"}</span>
      </footer>
    </section>
  );
}
