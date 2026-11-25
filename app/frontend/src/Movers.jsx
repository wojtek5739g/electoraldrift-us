import { useMemo, useState } from "react";

const TABS = [
  { id: "abs", label: "Largest shifts" },
  { id: "rep", label: "Toward REP" },
  { id: "dem", label: "Toward DEM" },
];
const OPEN_KEY = "edus-movers-open";
const time = (iso) => new Date(iso).toLocaleTimeString("en-GB");
const pp = (m) => `${m > 0 ? "R" : "D"} +${Math.abs(m).toFixed(2)}`;
const signed = (n) => `${n > 0 ? "+" : n < 0 ? "−" : "±"}${Math.abs(n).toLocaleString("en-US")}`;

function readOpen() {
  try { return localStorage.getItem(OPEN_KEY) !== "0"; } catch { return true; }
}

/** Top 10 counties by margin change between the selected timeline point and the one before it. */
export default function Movers({ current, previous, names }) {
  const [open, setOpen] = useState(readOpen);
  const [tab, setTab] = useState("abs");

  const toggle = () => {
    setOpen((o) => {
      try { localStorage.setItem(OPEN_KEY, o ? "0" : "1"); } catch { /* storage blocked */ }
      return !o;
    });
  };

  const rows = useMemo(() => {
    if (!current || !previous) return [];
    const all = Object.entries(current.counties).map(([fips, c]) => {
      const p = previous.counties[fips];
      return {
        fips, name: names[fips] ?? fips, margin: c.margin_pp,
        delta: c.margin_pp - p.margin_pp,             // > 0 = moved toward REP
        dRep: c.rep - p.rep, dDem: c.dem - p.dem,
        flipped: Math.sign(c.margin_pp) !== Math.sign(p.margin_pp),
      };
    });
    const sorted =
      tab === "rep" ? all.filter((r) => r.delta > 0).sort((a, b) => b.delta - a.delta)
      : tab === "dem" ? all.filter((r) => r.delta < 0).sort((a, b) => a.delta - b.delta)
      : all.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    return sorted.slice(0, 10);
  }, [current, previous, names, tab]);

  const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.delta)));

  return (
    <div className={open ? "movers open" : "movers"}>
      <button className="mv-head" onClick={toggle} aria-expanded={open}>
        <span>Top 10 movers</span>
        {current && previous && <small>{time(previous.ts)} → {time(current.ts)}</small>}
        <span className="mv-chev" aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="mv-body">
          {!previous ? (
            <p className="mv-empty">{current ? "This is the 2024 baseline. Movers appear from prediction #1." : "Start the simulation to see movers."}</p>
          ) : (
            <>
              <div className="mv-tabs" role="tablist">
                {TABS.map((t) => (
                  <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>{t.label}</button>
                ))}
              </div>
              <ol className="mv-list">
                {rows.map((r, i) => (
                  <li key={r.fips}>
                    <span className="mv-rank">{i + 1}</span>
                    <div className="mv-main">
                      <div className="mv-line">
                        <span className="mv-name">{r.name}{r.flipped && <em className="mv-flip">flip</em>}</span>
                        <b className={r.delta > 0 ? "rep" : "dem"}>{pp(r.delta)} pp</b>
                      </div>
                      <div className="mv-bar" aria-hidden="true">
                        <i className={r.delta > 0 ? "r" : "d"} style={{ width: `${(Math.abs(r.delta) / maxAbs) * 50}%` }} />
                      </div>
                      <div className="mv-sub">
                        <span className="rep">R {signed(r.dRep)}</span>
                        <span className="dem">D {signed(r.dDem)}</span>
                        <span>now {pp(r.margin)}</span>
                      </div>
                    </div>
                  </li>
                ))}
                {rows.length === 0 && <li className="mv-empty">No county moved in this direction.</li>}
              </ol>
            </>
          )}
        </div>
      )}
    </div>
  );
}
