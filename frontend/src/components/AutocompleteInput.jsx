import { useEffect, useRef, useState } from "react";
import { useSuggestions } from "../useSuggestions";

// Wraps a plain text <input> with a suggestions dropdown drawn from the app's
// bounded primitive-name vocabulary (see CLAUDE.md's 2026-08-14 queued item and
// useSuggestions.js). Two callers need different notions of "what am I typing" and
// "what does picking a suggestion produce": AliasAdder is a single free-text value
// (query == value, picking a suggestion replaces the whole thing), while
// DecompositionForm's parts field is a comma-separated list (query is just the
// segment after the last comma, picking a suggestion replaces only that segment and
// leaves the rest of the list alone) — `getQuery`/`applySuggestion` let each caller
// supply that logic instead of this component guessing at it.
export default function AutocompleteInput({
  value,
  onChange,
  getQuery = (v) => v,
  applySuggestion = (_v, suggestion) => suggestion,
  inputRef: externalRef,
  ...inputProps
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const wrapRef = useRef(null);
  const ownInputRef = useRef(null);
  const inputRef = externalRef ?? ownInputRef;
  const suggestions = useSuggestions(open ? getQuery(value) : "");

  useEffect(() => {
    setActiveIndex(-1);
  }, [suggestions]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function pick(suggestion) {
    onChange(applySuggestion(value, suggestion));
    setOpen(false);
    inputRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      pick(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const showDropdown = open && suggestions.length > 0;

  return (
    <div className="autocomplete-wrap" ref={wrapRef}>
      <input
        {...inputProps}
        ref={inputRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        role="combobox"
        aria-expanded={showDropdown}
        aria-autocomplete="list"
        autoComplete="off"
      />
      {showDropdown && (
        <div className="autocomplete-suggestions" role="listbox">
          {suggestions.map((s, i) => (
            <button
              key={s}
              type="button"
              role="option"
              aria-selected={i === activeIndex}
              className={`autocomplete-suggestion ${i === activeIndex ? "autocomplete-suggestion-active" : ""}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
