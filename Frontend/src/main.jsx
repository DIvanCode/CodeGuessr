import { Fragment, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Atlas, LEVELS, describeIds } from "./Atlas.jsx";
import { CodeExplorer } from "./CodeExplorer.jsx";
import { LanguagePie } from "./LanguagePie.jsx";
import { totalShare } from "./language-shares.js";
import "./style.css";

const TOTAL = 5;
const YEAR = new Date().getFullYear();
const STORAGE_KEY = "codeguessr.demo.v3";
const format = new Intl.NumberFormat("ru-RU");
const blankDraft = () => ({
  repository: "", label: "", pin: null, choice: null, depth: null, year: null, languages: {}, stars: null,
});
const blankGame = (world = null, difficulty = "easy") => ({
  history: [], roundId: null, fileId: 0, draft: blankDraft(), world, difficulty,
});
const worldOf = map => ({ id: map.id, owner: map.owner, total: Math.min(TOTAL, map.repositories.length) });
const mapKey = (owner, id, difficulty) => (owner ? id : `demo:${difficulty}`);
const emptyMap = { regions: [], groups: [], repositories: [], language_options: [] };
const DIFFICULTIES = [
  ["easy", "Лёгкий", "Материк → репозиторий. 2 файла по 35 строк"],
  ["medium", "Средний", "Материк → группа → репозиторий. Больше репозиториев, 3 файла по 50 строк"],
  ["hard", "Сложный", "Материк → группа → репозиторий → папка. До 300 репозиториев, 4 файла по 70 строк из одной папки"],
];
const hints = [
  ["context", "Показать строки выше"],
  ["path", "Путь к файлу"],
  ["region", "Показать материк"],
  ["stars", "Подсказать звёзды"],
  ["languages", "Подсказать список языков"],
];

function readGame() {
  try {
    const game = JSON.parse(sessionStorage.getItem(STORAGE_KEY)) ?? blankGame();
    return LEVELS[game.difficulty] ? game : blankGame(game.world);
  } catch {
    return blankGame();
  }
}

async function api(path, data, signal) {
  const response = await fetch(`/api${path}`, data === undefined ? { signal } : { signal,
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  if (response.ok) return response.json();
  const body = await response.json().catch(() => ({}));
  const error = new Error(typeof body.detail === "string" ? body.detail : "Не удалось выполнить запрос.");
  error.status = response.status;
  throw error;
}

function storeResult(game, round) {
  if (!round.result || game.history.some(entry => entry.id === round.id)) return game;
  return {
    ...game,
    history: [...game.history, { id: round.id, score: round.result.score, target: round.result.answer.repository_id }],
  };
}

function OwnerForm({ disabled, onStart }) {
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (!link.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await onStart(link.trim());
      setLink("");
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="owner-form" onSubmit={submit}>
      <input type="text" maxLength={200} value={link} placeholder="github.com/организация или пользователь"
        aria-label="Ссылка на пользователя или организацию GitHub" aria-describedby="owner-error"
        onChange={event => { setLink(event.target.value); setError(""); }} />
      <button type="submit" disabled={disabled || busy || !link.trim()}>{busy ? "Строим карту…" : "Своя карта"}</button>
      {error && <p id="owner-error" className="owner-error" role="alert">{error}</p>}
    </form>
  );
}

function DifficultyPicker({ value, disabled, onChange }) {
  return (
    <div className="difficulty" role="radiogroup" aria-label="Сложность">
      {DIFFICULTIES.map(([key, label, description]) => (
        <button key={key} type="button" role="radio" aria-checked={value === key} title={description}
          disabled={disabled} onClick={() => value !== key && onChange(key)}>{label}</button>
      ))}
    </div>
  );
}

function Editor({ round, file, onFile }) {
  return (
    <div className="editor">
      <div className="editor-bar">
        <div className="files" aria-label="Доступные файлы">
          {round.files.map(item => (
            <button key={item.id} type="button" aria-pressed={item.id === file.id} onClick={() => onFile(item.id)}>{item.name}</button>
          ))}
        </div>
        <span id="line-count">{file.lines.length} строк</span>
      </div>
      <div key={file.id} className="code" tabIndex={0} aria-label="Фрагмент кода">
        {file.lines.map((line, index) => (
          <div className="code-line" key={file.start + index}>
            <span className="line-number" aria-hidden="true">{file.start + index}</span>
            {/* The API escapes the source and adds Pygments syntax spans. */}
            <span className="line-text" dangerouslySetInnerHTML={{ __html: line }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function starLabel(stars) {
  return stars === 0 ? "<10" : `${stars}+`;
}

function GuessForm({ draft, languageOptions, starBands, onDraft, onSubmit, pending }) {
  const yearValue = draft.year ?? Math.round((2008 + YEAR) / 2);
  const hasLocation = Boolean(draft.repository || draft.pin);
  const [languagesConfirmed, setLanguagesConfirmed] = useState(false);
  const languageStep = useRef(null);
  const yearStep = useRef(null);
  const showDetails = hasLocation && languagesConfirmed;

  useEffect(() => {
    if (!hasLocation) return;
    const step = showDetails ? yearStep : languageStep;
    step.current?.focus({ preventScroll: !showDetails && !window.matchMedia("(max-width: 849px)").matches });
  }, [hasLocation, showDetails]);

  return (
    <form onSubmit={showDetails ? onSubmit : event => event.preventDefault()}>
      <div className="submit-card">
        <div>
          <small>1 · Выбери репозиторий на карте</small>
          <div id="selection">{draft.label || draft.repository || (draft.pin ? "Пин поставлен в море" : "Выберите место на карте или найдите репозиторий")}</div>
        </div>
        {hasLocation && (
          <button type="button" className="clear-year" onClick={() => {
            setLanguagesConfirmed(false);
            onDraft({ repository: "", label: "", pin: null, choice: null, depth: null });
          }}>Убрать выбор</button>
        )}
      </div>
      {hasLocation && (
        <div className="guess-step">
          <h2 ref={languageStep} tabIndex={-1}>2 · Топ языков репозитория</h2>
          <LanguagePie options={languageOptions} shares={draft.languages} onChange={languages => onDraft({ languages })} />
          {!languagesConfirmed && (
            <button type="button" className="primary submit-guess" onClick={() => setLanguagesConfirmed(true)}>Далее</button>
          )}
        </div>
      )}
      {showDetails && (
        <>
          <div className="guess-step">
            <div className="year">
              <div className="year-label">
                <h2 ref={yearStep} tabIndex={-1}><label htmlFor="year">3 · Год создания репозитория</label></h2>
                <output htmlFor="year">{draft.year ?? "—"}</output>
              </div>
              <input id="year" name="year" type="range" min={2008} max={YEAR} value={yearValue}
                onChange={event => onDraft({ year: Number(event.target.value) })} />
              <div className="ticks" aria-hidden="true">
                {Array.from({ length: 5 }, (_, index) => {
                  const year = Math.round(2008 + (YEAR - 2008) * index / 4);
                  return <span key={index}>{year}</span>;
                })}
              </div>
              {draft.year !== null && <button type="button" className="clear-year" onClick={() => onDraft({ year: null })}>Сбросить год</button>}
            </div>
          </div>
          <div className="guess-step">
            <h2 id="stars-heading">4 · Звёзды на GitHub</h2>
            <fieldset className="star-field" aria-labelledby="stars-heading">
              <div className="star-bands">
                {starBands.map((stars, index) => {
                  const upper = starBands[index + 1];
                  const range = upper === undefined ? `от ${format.format(stars)}` : `${format.format(stars)}–${format.format(upper - 1)}`;
                  return (
                    <button type="button" key={stars} aria-pressed={draft.stars === stars} title={`${range} звёзд`}
                      onClick={() => onDraft({ stars: draft.stars === stars ? null : stars })}>{starLabel(stars)}</button>
                  );
                })}
              </div>
            </fieldset>
            <button type="submit" className="primary submit-guess" disabled={pending}>Угадать</button>
          </div>
        </>
      )}
    </form>
  );
}

function HintValues({ values }) {
  return (
    <div className="hint-values" aria-live="polite">
      {values.languages && <div><strong>Языки</strong><span>{values.languages.join(" · ")}</span></div>}
      {values.stars !== undefined && <div><strong>Звёзды</strong><span>{format.format(values.stars)}</span></div>}
    </div>
  );
}

function sharesLabel(shares) {
  return Object.entries(shares).sort((a, b) => b[1] - a[1]).map(([name, share]) => `${name} ${share}%`).join(", ");
}

function Result({ result, data, draft, finished, score, onNext }) {
  const { answer, breakdown, penalty } = result;
  const nextButton = useRef(null);
  useEffect(() => { nextButton.current?.focus(); }, []);
  return (
    <section className="result" aria-live="polite">
      <div className="result-header">
        <h2><a href={answer.url} target="_blank" rel="noreferrer">{answer.full_name}</a></h2>
        <strong className="result-score">{format.format(result.score)} / {format.format(result.max_score)}</strong>
      </div>
      <dl>
        {[
          ["repository", "Место", describeIds(data, { ...answer, repository: answer.repository_id })],
          [null, "Ваш выбор", describeIds(data, result.location) || "мимо суши"], ["year", "Год", answer.year],
          ["languages", "Языки", sharesLabel(answer.languages)], ["stars", "Звёзды", format.format(answer.stars)],
          [null, "Размер", `≈ ${format.format(answer.size_mb)} МБ`],
        ].map(([key, label, value]) => (
          <Fragment key={label}><dt>{label}</dt><dd>{value}</dd><dd className="points">{key && `+${format.format(breakdown[key])}`}</dd></Fragment>
        ))}
        {penalty > 0 && <><dt>Подсказки</dt><dd /><dd className="points">−{format.format(penalty)}</dd></>}
      </dl>
      <p className="guess-shares">
        Ваши доли: {sharesLabel({
          ...draft.languages,
          ...(totalShare(draft.languages) < 100 ? { None: 100 - totalShare(draft.languages) } : {}),
        })}
      </p>
      <div className="source-links">
        {answer.files.map(file => <a key={file.path} href={file.url} target="_blank" rel="noreferrer">{file.path}</a>)}
      </div>
      <div className="result-footer">
        <strong>{finished ? `Игра окончена · ${format.format(score)} очков` : ""}</strong>
        <button ref={nextButton} type="button" className="primary" onClick={onNext}>{finished ? "Новая игра" : "Следующий раунд"}</button>
      </div>
    </section>
  );
}

function App() {
  const [game, setGame] = useState(readGame);
  const [data, setData] = useState(emptyMap);
  const [round, setRound] = useState(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [folders, setFolders] = useState({});
  const total = game.world?.total ?? TOTAL;
  const [hasContext, setHasContext] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const finished = game.history.length;
  const score = game.history.reduce((sum, item) => sum + item.score, 0);
  const number = Math.min(total, round?.result ? finished : finished + 1);
  const file = round?.files[game.fileId] ?? round?.files[0];
  const hasGraph = file?.entry_node_id != null;

  function selectFile(fileId) {
    setGame(previous => ({ ...previous, fileId }));
  }

  useEffect(() => {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(game)); } catch { /* Play without browser storage. */ }
  }, [game]);

  useEffect(() => { load(game); }, []);

  async function loadMap(current) {
    const id = current.world?.id ?? null;
    const loadedKey = mapKey(data.owner, data.id, data.difficulty);
    if (data.repositories.length && loadedKey === mapKey(current.world, id, current.difficulty)) return [data, current];
    if (!current.world) return [await api(`/map?difficulty=${current.difficulty}`), current];
    try {
      return [await api(`/worlds/${id}`), current];
    } catch (failure) {
      if (failure.status !== 404) throw failure;
    }
    const rebuilt = await api("/worlds", { url: current.world.owner, difficulty: current.difficulty });
    return [rebuilt, { ...current, world: worldOf(rebuilt) }];
  }

  function showMap(map) {
    if (map.id !== data.id) setFolders({});
    setData(map);
  }

  async function needFolders(ids) {
    const mapId = data.id;
    setFolders(previous => ({ ...previous, ...Object.fromEntries(ids.map(id => [id, "loading"])) }));
    await Promise.all(ids.map(async id => {
      let value = "failed";
      try {
        value = (await api(`/worlds/${mapId}/repositories/${id}/folders`)).folders;
      } catch (failure) {
        setError(failure.message);
      }
      setFolders(previous => ({ ...previous, [id]: value }));
    }));
  }

  async function load(initial, preloadedMap = null) {
    setPending(true);
    setRound(null);
    setError("");
    try {
      const [map, withMap] = preloadedMap ? [preloadedMap, initial] : await loadMap(initial);
      showMap(map);
      let current = withMap;
      const rounds = current.world?.total ?? TOTAL;
      let loaded;
      if (current.roundId) {
        try {
          loaded = await api(`/rounds/${current.roundId}`);
        } catch (failure) {
          if (failure.status !== 404) throw failure;
          current = current.history.length >= rounds ? blankGame(current.world) : { ...current, roundId: null, fileId: 0, draft: blankDraft() };
        }
      }
      loaded ??= await api("/rounds", {
        exclude: current.history.map(item => item.target), world: current.world?.id, difficulty: current.difficulty,
      });
      setRound(loaded);
      setGame(storeResult({ ...current, roundId: loaded.id }, loaded));
    } catch (failure) {
      setError(failure.message);
    } finally {
      setPending(false);
    }
  }

  function draft(values) {
    setGame(previous => ({ ...previous, draft: { ...previous.draft, ...values } }));
  }

  async function act(action, payload) {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      const updated = await api(`/rounds/${round.id}/${action}`, payload);
      setRound(updated);
      setGame(previous => storeResult(previous, updated));
    } catch (failure) {
      if (failure.status === 404) {
        await load(game);
        return;
      }
      setError(failure.message);
    } finally {
      setPending(false);
    }
  }

  function submit(event) {
    event.preventDefault();
    const { repository, pin, depth, languages, stars, year } = game.draft;
    if (repository || pin) act("guess", { repository, pin, depth, languages, stars, year });
  }

  function next() {
    const newGame = finished >= total
      ? blankGame(game.world, game.difficulty)
      : { ...game, roundId: null, fileId: 0, draft: blankDraft() };
    setGame(newGame);
    load(newGame);
  }

  async function startWorld(link, difficulty = game.difficulty) {
    const map = await api("/worlds", { url: link, difficulty });
    const newGame = blankGame(worldOf(map), difficulty);
    setGame(newGame);
    await load(newGame, map);
  }

  function leaveWorld() {
    const newGame = blankGame(null, game.difficulty);
    setGame(newGame);
    load(newGame);
  }

  async function changeDifficulty(difficulty) {
    if (!game.world) {
      const newGame = blankGame(null, difficulty);
      setGame(newGame);
      load(newGame);
      return;
    }
    setPending(true);
    setError("");
    try {
      await startWorld(game.world.owner, difficulty);
    } catch (failure) {
      setError(failure.message);
      setPending(false);
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="logo">CODE<span>GUESSR</span></div>
        <div className="rounds" aria-label={`Завершено раундов: ${finished} из ${total}`}>
          {Array.from({ length: total }, (_, index) => <span aria-hidden="true" key={index}
            className={`round-dot${index < finished ? " done" : index === finished ? " current" : ""}`} />)}
        </div>
        <DifficultyPicker value={game.difficulty} disabled={pending} onChange={changeDifficulty} />
        <OwnerForm disabled={pending} onStart={link => startWorld(link)} />
        <div className="total">Очки <strong>{format.format(score)}</strong></div>
      </header>
      <main className="layout">
        <section className="game" aria-labelledby="round-label">
          <div className="round-heading">
            <h1 id="round-label">Раунд {number} из {total} · Откуда этот код?</h1>
            {game.world ? (
              <span className="world-badge">
                <a className="demo-badge" href={`https://github.com/${game.world.owner}`} target="_blank" rel="noreferrer">@{game.world.owner}</a>
                <button type="button" className="demo-badge" disabled={pending} onClick={leaveWorld}>К демо</button>
              </span>
            ) : <span className="demo-badge">Демо</span>}
          </div>
          {!round ? (
            <div className="loading" role="status">
              <p>{error || "Загружаем задание…"}</p>
              {error && <button type="button" onClick={() => load(game)}>Попробовать снова</button>}
            </div>
          ) : (
            <>
              {!round.result && <HintValues values={round.hint_values} />}
              {hasGraph ? (
                <CodeExplorer key={round.id} round={round} file={file} api={api}
                  onContextAvailable={setHasContext} onFile={selectFile}
                  graphOpen={graphOpen} onGraphToggle={() => setGraphOpen(open => !open)} />
              ) : (
                <Editor key={round.id} round={round} file={file} onFile={selectFile} />
              )}
              {error && <p className="error" role="status">{error}</p>}
              {!round.result && (
                <div className="hints">
                  {hints.map(([kind, label]) => (
                    <button key={kind} type="button" onClick={() => act("hint", { kind })}
                      disabled={pending || round.hints[kind] || (kind === "context" && !(hasGraph ? hasContext : file.has_context))}>
                      {label} <span>{round.hints[kind] ? "✓" : `−${round.hint_costs[kind]}`}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
        <Atlas key={round?.id ?? "loading"} data={data} difficulty={data.difficulty ?? game.difficulty}
          folders={folders} onNeedFolders={needFolders} enabled={Boolean(round && !round.result && !pending)}
          ownerMap={Boolean(game.world)} choice={game.draft.choice} pin={game.draft.pin} result={round?.result} hint={round?.region}
          onChoose={draft}>
          {round && (round.result
            ? <Result result={round.result} data={data} draft={game.draft} finished={finished >= total} score={score} onNext={next} />
            : <GuessForm draft={game.draft} languageOptions={data.language_options} starBands={round.star_bands}
              onDraft={draft} onSubmit={submit} pending={pending} />)}
        </Atlas>
      </main>
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
