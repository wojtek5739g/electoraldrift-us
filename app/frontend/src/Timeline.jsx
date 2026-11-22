import { useEffect, useState } from "react";

const time = (iso) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const margin = (m) => (m == null ? "–" : `${m > 0 ? "R" : "D"} +${Math.abs(m).toFixed(2)}`);

function useNow(enabled) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [enabled]);
  return now;
}

export default function Timeline({ sim }) {
  const { meta, points, selected, following, speed, nextAt, error } = sim;
  const running = meta && !meta.done;
  const now = useNow(running);
  const speeds = meta?.speeds ?? [1, 10, 60];

  const total = meta?.total_points ?? 31;
  const lastIdx = Math.max(0, points.length - 1);
  const releasedPct = total > 1 ? (lastIdx / (total - 1)) * 100 : 0;
  const t0 = meta && new Date(meta.started_at).getTime();
  const endIso = meta && new Date(t0 + (total - 1) * meta.interval_s * 1000).toISOString();
  const secsLeft = nextAt ? Math.max(0, Math.ceil((nextAt - now) / 1000)) : null;

  return (
    <div className="timeline">
      <div className="tl-controls">
        <button className="tl-start" onClick={sim.start}>{meta ? "Restart simulation" : "Start simulation"}</button>
        {running && <button className="tl-stop" onClick={sim.stop}>■ Stop simulation</button>}
        <div className="tl-speed" role="group" aria-label="Simulation speed">
          {speeds.map((s) => (
            <button key={s} className={s === speed ? "on" : ""} onClick={() => sim.setSpeed(s)} aria-pressed={s === speed}>{s}×</button>
          ))}
        </div>
        <div className="tl-status">
          {!meta && "Each user gets their own timeline: one prediction every 60 s."}
          {running && <>Prediction <b>{points.length - 1}</b> / {total - 1} · next in <b>{secsLeft}s</b></>}
          {meta?.done && (meta.stopped
            ? <>Stopped at prediction {points.length - 1} / {total - 1}</>
            : <>Complete · {total - 1} predictions</>)}
        </div>
        {meta && (following
          ? <span className="tl-live">{running ? "● Live" : "Latest"}</span>
          : <button className="tl-follow" onClick={sim.followLatest}>Jump to latest ⇥</button>)}
      </div>

      {meta && points.length > 0 && (
        <>
          <div className="tl-track" style={{ "--released": `${releasedPct}%` }}>
            <input
              type="range" min={0} max={total - 1} step={1}
              value={selected?.seq ?? 0}
              onChange={(e) => sim.select(Math.min(Number(e.target.value), lastIdx))}
              aria-label="Timeline position"
              aria-valuetext={selected ? `${time(selected.ts)}, margin ${margin(selected.summary.margin_pp)}` : undefined}
            />
            <div className="tl-ticks" aria-hidden="true">
              {Array.from({ length: total }, (_, i) => <span key={i} className={i <= lastIdx ? "in" : ""} />)}
            </div>
          </div>
          <div className="tl-labels">
            <span>{time(meta.started_at)}</span>
            {selected && (
              <span className="tl-now">
                {time(selected.ts)} · {selected.kind === "baseline" ? "2024 baseline" : `prediction #${selected.seq}`} · statewide{" "}
                <b className={selected.summary.margin_pp > 0 ? "rep" : "dem"}>{margin(selected.summary.margin_pp)}</b>
              </span>
            )}
            <span>{time(endIso)}</span>
          </div>
        </>
      )}
      {error && <div className="error">Simulation error: {error}</div>}
    </div>
  );
}
