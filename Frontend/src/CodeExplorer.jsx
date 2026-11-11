import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { CallGraph } from "./CallGraph.jsx";

export function CodeExplorer({ round, file, onFile, onContextAvailable, api }) {
  const [selection, setSelection] = useState({ nodeId: file.entry_node_id, scrollTop: 0, scrollLeft: 0, expanded: {} });
  const positions = useRef({});
  const cache = useRef(new Map());
  const [view, setView] = useState(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const code = useRef(null);
  // Hints change the source/path we may display. Keep those cache versions separate.
  const version = `${round.id}:${Boolean(round.hints.context)}:${Boolean(round.hints.path)}:${Boolean(round.result)}`;
  const key = `${version}:${selection.nodeId}`;
  const cached = cache.current.get(key);
  const graph = cached ?? view?.graph;
  const isCurrent = Boolean(cached);
  const displayedSelection = isCurrent ? selection : view?.selection;

  useEffect(() => {
    onContextAvailable(isCurrent && Boolean(graph?.source?.has_context));
  }, [graph, isCurrent, onContextAvailable]);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    if (cache.current.has(key)) {
      setView({ graph: cache.current.get(key), selection });
      return;
    }
    api(`/rounds/${round.id}/graph/${selection.nodeId}`, undefined, controller.signal)
      .then(value => {
        if (!controller.signal.aborted) {
          cache.current.set(key, value);
          setView({ graph: value, selection });
        }
      })
      .catch(failure => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [key, retry, api]);

  useLayoutEffect(() => {
    if (isCurrent && code.current) {
      code.current.scrollTop = selection.scrollTop;
      code.current.scrollLeft = selection.scrollLeft;
    }
  }, [graph, isCurrent, selection.nodeId, file.id]);

  function navigate(nodeId) {
    if (!isCurrent || nodeId === selection.nodeId) return;
    setView({ graph, selection });
    setError("");
    setSelection({ nodeId, scrollTop: 0, scrollLeft: 0, expanded: {} });
  }

  function chooseFile(item) {
    if (item.id === file.id) return;
    positions.current[file.id] = {
      ...selection,
      scrollTop: isCurrent ? code.current?.scrollTop ?? selection.scrollTop : selection.scrollTop,
      scrollLeft: isCurrent ? code.current?.scrollLeft ?? selection.scrollLeft : selection.scrollLeft,
    };
    if (isCurrent) setView({ graph, selection });
    setError("");
    setSelection(positions.current[item.id] ?? { nodeId: item.entry_node_id, scrollTop: 0, scrollLeft: 0, expanded: {} });
    onFile(item.id);
  }

  const source = graph?.source;
  return (
    <section className="editor" aria-label="Исследование кода" aria-busy={!isCurrent && !error}>
      <div className="editor-bar">
        <div className="files" aria-label="Начальные фрагменты">
          {round.files.map(item => <button key={item.id} type="button" aria-pressed={file.id === item.id}
            onClick={() => chooseFile(item)}>{item.name}</button>)}
        </div>
      </div>
      <div className="graph-toolbar">
        <strong>Граф вызовов</strong><span>Прямые связи · 1 шаг</span>
        <div><button type="button" onClick={() => navigate(file.entry_node_id)} disabled={!isCurrent || selection.nodeId === file.entry_node_id}>К началу</button></div>
      </div>
      {error && <div className="graph-message" role="alert"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Повторить</button></div>}
      {!graph ? !error && <div className="graph-message" role="status">Загружаем связи…</div> : (
          <>
            <CallGraph graph={graph} onNavigate={navigate} expanded={displayedSelection.expanded} disabled={!isCurrent}
              onExpand={side => setSelection(previous => ({ ...previous, expanded: { ...previous.expanded, [side]: !previous.expanded[side] } }))} />
            <div className="source-bar" aria-live="polite"><strong>{graph.node.name}</strong><span>{source ? `${source.name} · ${source.lines.length} строк` : "Исходник вне демо"}</span></div>
            {source ? <div ref={code} key={graph.node.id} className="code" tabIndex={0} aria-label={`Код ${graph.node.name}`}>
              {source.lines.map((line, index) => <div className="code-line" key={source.start + index}>
                <span className="line-number" aria-hidden="true">{source.start + index}</span>
                <span className="line-text" dangerouslySetInnerHTML={{ __html: line }} />
              </div>)}
            </div> : <div className="graph-message">Код этой функции не включён в демо. Перейдите к вызывающей функции или выберите начальный фрагмент.</div>}
          </>
        )}
    </section>
  );
}
