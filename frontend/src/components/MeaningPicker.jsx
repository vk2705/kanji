import { useState } from "react";
import Glyph from "./Glyph";
import { t } from "../i18n";

// Shown under a parts search when a typed name means more than one thing ("lid" is
// the primitive 亠 and the kanji 蓋). Every meaning starts switched on, so the
// search finds all of them; switching one off narrows the search to the rest.
//
// `meanings` is the search response's {term: [option]} map. `choice` is
// {term: [ids]} for the terms the user has narrowed; a term missing from it has
// every option on. Hanzi that answer to the name only because it is their pinyin
// (孙 is read "sun") arrive with via: "reading" and are folded into one chip, and a
// long list shows its first few options until expanded.
const VISIBLE_OPTIONS = 6;

export default function MeaningPicker({ meanings, choice, onChange, lang }) {
  const tt = (key, ...args) => t(lang, key, ...args);
  const [expanded, setExpanded] = useState({});
  const terms = Object.keys(meanings || {});
  if (!terms.length) return null;

  return (
    <div className="meaning-picker">
      <p className="meaning-picker-hint">{tt("meaningHint")}</p>
      {terms.map((term) => {
        const options = meanings[term];
        const byName = options.filter((o) => o.via !== "reading");
        const byReading = options.filter((o) => o.via === "reading");
        const allIds = options.flatMap((o) => o.ids);
        const selected = new Set(choice[term] ?? allIds);
        const isOn = (ids) => ids.some((id) => selected.has(id));

        function toggle(ids) {
          const next = new Set(selected);
          if (isOn(ids)) ids.forEach((id) => next.delete(id));
          else ids.forEach((id) => next.add(id));
          // At least one meaning has to stay on, or there is nothing to search for.
          if (next.size === 0) return;
          onChange(term, next.size === allIds.length ? null : allIds.filter((id) => next.has(id)));
        }

        const chips = byName.map((o) => ({ key: o.ids[0], ids: o.ids, option: o }));
        if (byReading.length) {
          chips.push({ key: "reading", ids: byReading.flatMap((o) => o.ids), reading: byReading.length });
        }
        const showAll = expanded[term] || chips.length <= VISIBLE_OPTIONS + 1;
        const shown = showAll ? chips : chips.slice(0, VISIBLE_OPTIONS);

        return (
          <div className="meaning-row" key={term}>
            <span className="meaning-term">{term}:</span>
            {shown.map((chip) => (
              <button
                key={chip.key}
                type="button"
                className={`meaning-chip ${isOn(chip.ids) ? "meaning-chip-on" : ""}`}
                aria-pressed={isOn(chip.ids)}
                onClick={() => toggle(chip.ids)}
                title={chip.option ? chip.option.keyword : undefined}
              >
                {chip.option ? (
                  <>
                    <span className="meaning-glyph">
                      <Glyph
                        character={chip.option.character}
                        imageUrl={chip.option.image_url}
                        keyword={chip.option.keyword}
                        id={chip.option.ids[0]}
                        imgClassName="part-chip-img"
                      />
                    </span>
                    <span className="meaning-kind">{tt(`meaningKind_${chip.option.kind}`)}</span>
                  </>
                ) : (
                  <span className="meaning-kind">{tt("meaningReading", chip.reading, term)}</span>
                )}
              </button>
            ))}
            {!showAll && (
              <button
                type="button"
                className="meaning-more"
                onClick={() => setExpanded({ ...expanded, [term]: true })}
              >
                {tt("meaningMore", chips.length - VISIBLE_OPTIONS)}
              </button>
            )}
            {choice[term] && (
              <button type="button" className="meaning-more" onClick={() => onChange(term, null)}>
                {tt("meaningAll")}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
