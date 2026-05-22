import { useMemo, useState } from "react";
import type { PaperRecord, SortKey } from "../types";
import PaperRow from "./PaperRow";

interface Props {
  papers: PaperRecord[];
}

export default function ResultsTable({ papers }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [asc, setAsc] = useState(false);

  const sorted = useMemo(() => {
    const arr = [...papers];
    arr.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "score") cmp = a.score - b.score;
      else if (sortKey === "year") cmp = (a.year ?? 0) - (b.year ?? 0);
      else cmp = a.title.localeCompare(b.title);
      return asc ? cmp : -cmp;
    });
    return arr;
  }, [papers, sortKey, asc]);

  function toggle(k: SortKey) {
    if (k === sortKey) setAsc((v) => !v);
    else {
      setSortKey(k);
      setAsc(k === "title");
    }
  }

  function arrow(k: SortKey) {
    if (k !== sortKey) return null;
    return <span className="arrow">{asc ? "▲" : "▼"}</span>;
  }

  if (papers.length === 0) {
    return <div className="empty">No papers passed the filters for this step.</div>;
  }

  return (
    <div className="results-wrap">
      <table className="results">
        <thead>
          <tr>
            <th onClick={() => toggle("score")}>Score{arrow("score")}</th>
            <th onClick={() => toggle("title")}>Title / Authors{arrow("title")}</th>
            <th onClick={() => toggle("year")}>Year{arrow("year")}</th>
            <th>Journal</th>
            <th>Sources</th>
            <th>DOI</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <PaperRow key={p.doi ?? p.pmid ?? `${i}-${p.title}`} paper={p} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
