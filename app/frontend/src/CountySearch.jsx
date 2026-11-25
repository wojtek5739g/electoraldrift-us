import { useId, useMemo, useRef, useState } from "react";

/** Searchable county list (combobox). Picking a county calls onPick(fips). */
export default function CountySearch({ counties, onPick }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const listRef = useRef(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? counties.filter((c) => c.name.toLowerCase().includes(q)) : counties;
    // Names that start with the query first, then the rest; both alphabetical.
    return [...list].sort((a, b) =>
      (q && b.name.toLowerCase().startsWith(q)) - (q && a.name.toLowerCase().startsWith(q)) || a.name.localeCompare(b.name));
  }, [counties, query]);

  const pick = (c) => {
    onPick(c.fips);
    setQuery("");
    setOpen(false);
  };

  const move = (d) => {
    const n = Math.max(0, Math.min(matches.length - 1, active + d));
    setActive(n);
    listRef.current?.children[n]?.scrollIntoView({ block: "nearest" });
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter" && open && matches[active]) { e.preventDefault(); pick(matches[active]); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  return (
    <div className="csearch">
      <input
        type="search"
        placeholder={`Search ${counties.length} counties…`}
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && matches[active] ? `${listId}-${matches[active].fips}` : undefined}
        aria-label="Find a county"
      />
      {open && (
        <ul className="csearch-list" id={listId} role="listbox" ref={listRef}>
          {matches.map((c, i) => (
            <li
              key={c.fips}
              id={`${listId}-${c.fips}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "on" : ""}
              onMouseDown={(e) => { e.preventDefault(); pick(c); }} // mousedown: fires before the input blurs
              onMouseEnter={() => setActive(i)}
            >
              <span>{c.name}</span>
              <small className={c.margin > 0 ? "rep" : "dem"}>{c.margin > 0 ? "R" : "D"} +{Math.abs(c.margin).toFixed(2)}</small>
            </li>
          ))}
          {matches.length === 0 && <li className="csearch-none">No county matches “{query}”.</li>}
        </ul>
      )}
    </div>
  );
}
