import { useCallback, useEffect, useRef, useState } from "react";

const SESSION_KEY = "edus-session-id";

// crypto.randomUUID needs a secure context (https/localhost); getRandomValues works everywhere.
function uuid4() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// One id per browser: the key of this user's own timeline on the backend.
function getSessionId() {
  try {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) { id = uuid4(); localStorage.setItem(SESSION_KEY, id); }
    return id;
  } catch {
    return (getSessionId.fallback ??= uuid4()); // storage blocked: id lives for this page load only
  }
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/**
 * Per-user prediction timeline. `active` = the Live view is shown; polling only runs then.
 * selectedSeq === null means "follow latest": the view jumps to each new point as it arrives.
 */
export function useSimulation(active) {
  const sessionId = useRef(getSessionId()).current;
  const [meta, setMeta] = useState(null);       // backend state without points
  const [points, setPoints] = useState([]);
  const [selectedSeq, setSelectedSeq] = useState(null);
  const [speed, setSpeedState] = useState(1);
  const [nextAt, setNextAt] = useState(null);   // local ms timestamp of the next point
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const lastSeq = useRef(-1);
  const [pollGen, setPollGen] = useState(0);    // bump to restart the poll loop

  const absorb = useCallback((res, replace) => {
    const { points: incoming, ...rest } = res;
    setMeta(rest);
    setSpeedState(rest.speed);
    setNextAt(rest.next_in_s == null ? null : Date.now() + rest.next_in_s * 1000);
    if (replace) { lastSeq.current = -1; setPoints([]); }
    if (incoming.length) {
      lastSeq.current = incoming[incoming.length - 1].seq;
      setPoints((prev) => (replace ? incoming : [...prev, ...incoming]));
    }
  }, []);

  // Resume an earlier simulation of this session (e.g. after a page reload).
  useEffect(() => {
    if (!active || loaded) return;
    api(`/api/sim/${sessionId}`)
      .then((res) => { if (res) absorb(res, true); setLoaded(true); })
      .catch((e) => setError(String(e)));
  }, [active, loaded, sessionId, absorb]);

  // Poll right after the next point is due (at most every 5 s, at least 0.3 s apart).
  useEffect(() => {
    if (!active || !meta || meta.done) return;
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const res = await api(`/api/sim/${sessionId}?since=${lastSeq.current}`);
        if (cancelled) return;
        if (!res) { setMeta(null); setPoints([]); return; } // backend restarted, session gone
        absorb(res, false);
        setError(null);
        if (!res.done) timer = setTimeout(tick, Math.min(5000, Math.max(300, res.next_in_s * 1000 + 150)));
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        timer = setTimeout(tick, 5000);
      }
    };
    const wait = nextAt ? Math.min(5000, Math.max(300, nextAt - Date.now() + 150)) : 1000;
    timer = setTimeout(tick, wait);
    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, meta?.started_at, meta?.done, pollGen, sessionId, absorb]);

  const start = useCallback(async () => {
    try {
      const res = await api("/api/sim/start", { session_id: sessionId, speed });
      absorb(res, true);
      setSelectedSeq(null);
      setError(null);
      setPollGen((g) => g + 1);
    } catch (e) { setError(String(e)); }
  }, [sessionId, speed, absorb]);

  const stop = useCallback(async () => {
    try {
      const res = await api(`/api/sim/${sessionId}/stop`, {});
      if (res) absorb(res, false);
    } catch (e) { setError(String(e)); }
  }, [sessionId, absorb]);

  const setSpeed = useCallback(async (s) => {
    setSpeedState(s);
    if (!meta || meta.done) return; // before start: just remember the choice
    try {
      const res = await api(`/api/sim/${sessionId}/speed`, { speed: s });
      if (res) { absorb(res, false); setPollGen((g) => g + 1); }
    } catch (e) { setError(String(e)); }
  }, [meta, sessionId, absorb]);

  const latest = points.length ? points[points.length - 1] : null;
  const selected = selectedSeq == null ? latest : points.find((p) => p.seq === selectedSeq) ?? latest;
  const previous = selected ? points.find((p) => p.seq === selected.seq - 1) ?? null : null;

  return {
    sessionId, meta, points, selected, previous, following: selectedSeq == null, speed, nextAt, error,
    start, stop, setSpeed,
    select: (seq) => setSelectedSeq(latest && seq >= latest.seq ? null : seq),
    followLatest: () => setSelectedSeq(null),
  };
}
