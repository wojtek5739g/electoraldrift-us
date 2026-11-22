import { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { FlyToInterpolator, WebMercatorViewport } from "@deck.gl/core";
import { GeoJsonLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import Timeline from "./Timeline.jsx";
import Movers from "./Movers.jsx";
import CountySearch from "./CountySearch.jsx";
import { useSimulation } from "./useSimulation.js";

const BASEMAP = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const NC_VIEW = { longitude: -79.4, latitude: 35.25, zoom: 6.4, pitch: 0, bearing: 0 };

// Every feature that will ship later is listed here and rendered disabled.
const STATES = [{ id: "NC", label: "North Carolina", enabled: true }, { id: "ALL", label: "All other states", enabled: false }];
const YEARS = [{ id: 2024, enabled: true }, { id: 2020, enabled: false }, { id: 2016, enabled: false }, { id: 2012, enabled: false }];
const MODES = [
  { id: "results", label: "Certified results", enabled: true },
  { id: "live", label: "Live prediction (60 s)", enabled: true },
  { id: "absentee", label: "NC early & mail ballots", enabled: false },
];
const OVERLAYS = [
  { id: "nws", label: "NWS weather alerts" },
  { id: "faa", label: "FAA airport status" },
  { id: "disinfo", label: "Disinformation signals" },
];
const SLIDERS = [
  { id: "rain", label: "Precipitation on election day", unit: "mm" },
  { id: "unemp", label: "Unemployment change", unit: "pp" },
  { id: "delay", label: "Flight delays", unit: "min" },
];

const fmt = (n) => (n ?? 0).toLocaleString("en-US");

// Diverging colour: blue (DEM) … red (REP); intensity grows with |margin|, saturating at 40 pp.
function marginColor(m) {
  if (m == null || Number.isNaN(m)) return [200, 200, 200, 160];
  const t = Math.min(Math.abs(m) / 40, 1);
  const base = m > 0 ? [200, 40, 40] : [35, 85, 190];
  const mix = (c) => Math.round(245 + (c - 245) * (0.25 + 0.75 * t));
  return [...base.map(mix), 220];
}

// [minLon, minLat, maxLon, maxLat] of a GeoJSON geometry.
function bbox(geometry) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = (c) => {
    if (typeof c[0] === "number") { b[0] = Math.min(b[0], c[0]); b[1] = Math.min(b[1], c[1]); b[2] = Math.max(b[2], c[0]); b[3] = Math.max(b[3], c[1]); }
    else c.forEach(walk);
  };
  walk(geometry.coordinates);
  return b;
}

const PULSE_MS = 3000;
const marginText = (m) => (m == null ? "–" : `${m > 0 ? "R" : "D"} +${Math.abs(m).toFixed(2)}`);

function Soon({ children }) {
  return <span className="soon" title="Planned for a later milestone">{children}<em>soon</em></span>;
}

export default function App() {
  const [geo, setGeo] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [hover, setHover] = useState(null);
  const [mode, setMode] = useState("results");
  const live = mode === "live";
  const sim = useSimulation(live);
  const point = live ? sim.selected : null;
  const [selectedFips, setSelectedFips] = useState(null);
  const [viewState, setViewState] = useState(NC_VIEW);
  const mapRef = useRef(null);
  const [pulse, setPulse] = useState(1);
  const [finderOpen, setFinderOpen] = useState(() => { try { return localStorage.getItem("edus-finder-open") !== "0"; } catch { return true; } });
  const toggleFinder = () => setFinderOpen((o) => {
    try { localStorage.setItem("edus-finder-open", o ? "0" : "1"); } catch { /* storage blocked */ }
    return !o;
  });

  useEffect(() => {
    Promise.all([
      fetch("/api/results/2024/NC/counties").then((r) => (r.ok ? r.json() : Promise.reject(r.statusText))),
      fetch("/api/results/2024/NC/summary").then((r) => (r.ok ? r.json() : Promise.reject(r.statusText))),
    ]).then(([g, s]) => { setGeo(g); setSummary(s); }).catch((e) => setError(String(e)));
  }, []);

  // In Live mode, overlay the selected timeline point's county numbers onto the polygons.
  const shown = useMemo(() => {
    if (!geo || !point) return geo;
    return { ...geo, features: geo.features.map((f) => ({ ...f, properties: { ...f.properties, ...point.counties[f.properties.fips] } })) };
  }, [geo, point]);
  const shownSummary = point ? point.summary : summary;
  const countyNames = useMemo(() => Object.fromEntries((geo?.features ?? []).map((f) => [f.properties.fips, f.properties.name])), [geo]);
  // Read the hovered county from `shown` so the tooltip follows new timeline points.
  const hp = hover && shown?.features.find((f) => f.properties.fips === hover.object.properties.fips)?.properties;

  const searchList = useMemo(() => (shown?.features ?? []).map((f) => ({ fips: f.properties.fips, name: f.properties.name, margin: f.properties.margin_pp })), [shown]);
  const selectedFeature = shown?.features.find((f) => f.properties.fips === selectedFips) ?? null;

  // Counties whose winner changed between the previous and the selected timeline point.
  const flipped = useMemo(() => {
    if (!point || !sim.previous || !shown) return [];
    return shown.features.filter((f) => {
      const a = sim.previous.counties[f.properties.fips]?.margin_pp, b = point.counties[f.properties.fips]?.margin_pp;
      return a != null && b != null && Math.sign(a) !== Math.sign(b);
    });
  }, [shown, point, sim.previous]);
  const flippedSet = useMemo(() => new Set(flipped.map((f) => f.properties.fips)), [flipped]);

  // When a new set of flips appears, pulse it for PULSE_MS, then keep a steady glow.
  const flipKey = flipped.length ? `${sim.meta?.started_at}:${point?.seq}` : "";
  useEffect(() => {
    if (!flipKey) return;
    let raf;
    const t0 = performance.now();
    const step = (t) => {
      const e = t - t0;
      setPulse(e >= PULSE_MS ? 1 : 0.5 + 0.5 * Math.cos((e / 500) * Math.PI));
      if (e < PULSE_MS) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [flipKey]);

  // Select a county and (optionally) fly the camera to it, leaving room for the overlays.
  const selectCounty = (fips, fly = true) => {
    setSelectedFips(fips);
    const f = fips && geo?.features.find((x) => x.properties.fips === fips);
    const el = mapRef.current;
    if (!fly || !f || !el) return;
    const [x0, y0, x1, y1] = bbox(f.geometry);
    const pad = { top: 60, left: 340, bottom: live ? 170 : 60, right: live ? 360 : 60 };
    const fits = el.clientWidth > pad.left + pad.right + 50 && el.clientHeight > pad.top + pad.bottom + 50;
    const vp = new WebMercatorViewport({ width: el.clientWidth, height: el.clientHeight })
      .fitBounds([[x0, y0], [x1, y1]], { padding: fits ? pad : 20 });
    setViewState({
      longitude: vp.longitude, latitude: vp.latitude, zoom: Math.min(vp.zoom, 9.5), pitch: 0, bearing: 0,
      transitionDuration: 900, transitionInterpolator: new FlyToInterpolator(),
    });
  };

  const layers = useMemo(() => shown ? [
    new GeoJsonLayer({
      id: "counties-2024",
      data: shown,
      pickable: true,
      stroked: true,
      filled: true,
      getFillColor: (f) => marginColor(f.properties.margin_pp),
      getLineColor: [255, 255, 255, 230],
      lineWidthMinPixels: 0.7,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 90],
      onHover: (info) => setHover(info.object ? info : null),
      onClick: (info) => info.object && selectCounty(info.object.properties.fips, false),
      transitions: { getFillColor: 400 },
    }),
    // Yellow = county flipped since the previous prediction (pulses on arrival).
    flipped.length > 0 && new GeoJsonLayer({
      id: "flips",
      data: flipped,
      filled: true,
      stroked: true,
      getFillColor: [255, 214, 0, Math.round(110 + 130 * pulse)],
      getLineColor: [230, 160, 0, 255],
      getLineWidth: 2 + 2 * pulse,
      lineWidthUnits: "pixels",
      updateTriggers: { getFillColor: pulse, getLineWidth: pulse },
    }),
    // Selected county: white halo + dark outline so it reads on any fill.
    selectedFeature && new GeoJsonLayer({
      id: "selected-halo", data: [selectedFeature], filled: false, stroked: true,
      getLineColor: [255, 255, 255, 255], getLineWidth: 6, lineWidthUnits: "pixels",
    }),
    selectedFeature && new GeoJsonLayer({
      id: "selected", data: [selectedFeature], filled: false, stroked: true,
      getLineColor: [29, 35, 48, 255], getLineWidth: 3, lineWidthUnits: "pixels",
    }),
  ].filter(Boolean) : [], [shown, flipped, pulse, selectedFeature]);

  return (
    <div className="app">
      <aside className="panel">
        <h1>ElectoralDrift <span>US</span></h1>
        <p className="sub">2024 presidential election · {live ? "live predictions (mock)" : "county results"}</p>

        <section>
          <h2>State</h2>
          <div className="chips">
            {STATES.map((s) => (
              <button key={s.id} className={s.enabled ? "chip active" : "chip"} disabled={!s.enabled} aria-disabled={!s.enabled}>
                {s.enabled ? s.label : <Soon>{s.label}</Soon>}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2>Election</h2>
          <div className="chips">
            {YEARS.map((y) => (
              <button key={y.id} className={y.enabled ? "chip active" : "chip"} disabled={!y.enabled} aria-disabled={!y.enabled}>{y.id}</button>
            ))}
          </div>
        </section>

        <section>
          <h2>View</h2>
          {MODES.map((m) => (
            <label key={m.id} className={m.enabled ? "row" : "row disabled"}>
              <input type="radio" name="mode" checked={mode === m.id} onChange={() => { setMode(m.id); setHover(null); }} disabled={!m.enabled} />
              {m.enabled ? m.label : <Soon>{m.label}</Soon>}
            </label>
          ))}
        </section>

        <section>
          <h2>Overlays</h2>
          {OVERLAYS.map((o) => (
            <label key={o.id} className="row disabled">
              <input type="checkbox" disabled /> <Soon>{o.label}</Soon>
            </label>
          ))}
        </section>

        <section>
          <h2>Scenarios</h2>
          {SLIDERS.map((s) => (
            <label key={s.id} className="slider disabled">
              <Soon>{s.label}</Soon>
              <input type="range" min="-10" max="10" defaultValue="0" disabled />
            </label>
          ))}
        </section>

        <section className="disabled-block" aria-disabled="true">
          <h2><Soon>Electoral votes (270 to win)</Soon></h2>
          <div className="evbar"><div /></div>
        </section>

        <section>
          <h2>Statewide{point && ` · ${point.kind === "baseline" ? "baseline" : "predicted"} ${new Date(point.ts).toLocaleTimeString("en-GB")}`}</h2>
          {error && <p className="error">Could not load data: {error}</p>}
          {shownSummary && (
            <table className="sum">
              <tbody>
                <tr><td className="total">Total</td><td>{fmt(shownSummary.total)}</td></tr>
                <tr><td className="rep">Republican</td><td>{fmt(shownSummary.rep)}</td><td>{(shownSummary.rep / shownSummary.total * 100).toFixed(2)}%</td></tr>
                <tr><td className="dem">Democratic</td><td>{fmt(shownSummary.dem)}</td><td>{(shownSummary.dem / shownSummary.total * 100).toFixed(2)}%</td></tr>
                <tr><td>Other</td><td>{fmt(shownSummary.other)}</td><td>{(shownSummary.other / shownSummary.total * 100).toFixed(2)}%</td></tr>
              </tbody>
            </table>
          )}
          <div className="legend">
            <span>D +40</span><div className="ramp" /><span>R +40</span>
          </div>
          {live && <div className="legend"><i className="swatch-flip" /> County flipped since the previous prediction</div>}
          <p className="src">Source: MIT Election Data + Science Lab; US Census boundaries.{live && " Live predictions are mock data (random walk)."}</p>
        </section>
      </aside>

      <main className="map" ref={mapRef}>
        <DeckGL
          initialViewState={viewState}
          controller
          layers={layers}
          getCursor={({ isDragging }) => (isDragging ? "grabbing" : "var(--cursor-hand)")}
        >
          <Map mapStyle={BASEMAP} />
        </DeckGL>
        <div className={finderOpen ? "movers finder open" : "movers finder"}>
          <button className="mv-head" onClick={toggleFinder} aria-expanded={finderOpen}>
            <span>Find county</span>
            <small>{selectedFeature ? selectedFeature.properties.name : ""}</small>
            <span className="mv-chev" aria-hidden="true">{finderOpen ? "▾" : "▸"}</span>
          </button>
          {finderOpen && (
            <div className="mv-body">
              <CountySearch counties={searchList} onPick={(fips) => selectCounty(fips)} />
              {selectedFeature && (() => {
                const c = selectedFeature.properties;
                return (
                  <div className="ccard">
                    <div className="ccard-head">
                      <strong>{c.name} County</strong>
                      {flippedSet.has(c.fips) && <em className="mv-flip">flipped</em>}
                      <button className="ccard-x" onClick={() => setSelectedFips(null)} aria-label="Clear selected county">×</button>
                    </div>
                    <div className={c.margin_pp > 0 ? "rep" : "dem"}>Margin {marginText(c.margin_pp)}</div>
                    <table className="sum">
                      <tbody>
                        <tr><td className="rep">Rep</td><td>{fmt(c.rep)}</td><td>{(c.rep / c.total * 100).toFixed(2)}%</td></tr>
                        <tr><td className="dem">Dem</td><td>{fmt(c.dem)}</td><td>{(c.dem / c.total * 100).toFixed(2)}%</td></tr>
                        <tr><td>Other</td><td>{fmt(c.other)}</td><td>{(c.other / c.total * 100).toFixed(2)}%</td></tr>
                      </tbody>
                    </table>
                    <button className="ccard-zoom" onClick={() => selectCounty(c.fips)}>Zoom to county</button>
                  </div>
                );
              })()}
            </div>
          )}
        </div>
        {live && <Movers current={sim.selected} previous={sim.previous} names={countyNames} />}
        {live && <Timeline sim={sim} />}
        {hp && (
          <div className="tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
            <strong>{hp.name} County</strong>
            <div>Margin: {hp.margin_pp > 0 ? "R" : "D"} +{Math.abs(hp.margin_pp).toFixed(2)}</div>
            <div className="rep">Rep: {fmt(hp.rep)}</div>
            <div className="dem">Dem: {fmt(hp.dem)}</div>
            <div>Other: {fmt(hp.other)}</div>
            <div>Total: {fmt(hp.total)}</div>
          </div>
        )}
      </main>
    </div>
  );
}
