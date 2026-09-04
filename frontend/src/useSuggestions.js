import { useEffect, useRef, useState } from "react";
import { suggestTerms } from "./api";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 200;

// Debounced autocomplete lookup for the free-text primitive-name inputs (the parts
// field in DecompositionForm, alias-add inputs) — see CLAUDE.md's 2026-08-14 queued
// item. `query` is whatever substring the caller wants suggestions for (e.g. just the
// segment currently being typed in a comma-separated field, not necessarily the whole
// input value). A trailing-call-wins counter guards against an earlier, slower request
// clobbering a newer result if responses arrive out of order.
export function useSuggestions(query) {
  const [suggestions, setSuggestions] = useState([]);
  const latestRequestId = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      return;
    }
    const requestId = ++latestRequestId.current;
    const timer = setTimeout(async () => {
      try {
        const results = await suggestTerms(trimmed);
        if (latestRequestId.current === requestId) setSuggestions(results);
      } catch {
        // autocomplete is a convenience, not worth surfacing an error for
        if (latestRequestId.current === requestId) setSuggestions([]);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  return suggestions;
}
