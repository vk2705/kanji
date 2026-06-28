import KanjiCard from "./KanjiCard";

export default function ResultsGrid({ results, onSelect, loading }) {
  if (loading) return <div className="status">Searching…</div>;
  if (!results) return null;
  if (results.length === 0) return <div className="status">No results found.</div>;

  return (
    <div>
      <div className="results-count">{results.length} result{results.length !== 1 ? "s" : ""}</div>
      <div className="results-grid">
        {results.map((k) => (
          <KanjiCard key={k.id} kanji={k} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
