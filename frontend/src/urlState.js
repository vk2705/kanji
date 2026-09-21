// Encodes/decodes the shareable, back-button-restorable part of App's state into the
// URL query string, independent of Vite's `base` (see vite.config.js — the two
// deployment targets serve from different path prefixes, so this only ever touches
// `location.search`, never `location.pathname`).
//
// Only search inputs + the selected kanji + view are round-tripped. Anything
// per-account (uiLang, studyScript as an account preference) already persists via
// localStorage/the user's own profile, so putting it in the URL too would just create
// two disagreeing sources of truth when they diverge.

const TAB_NAMES = ["parts", "text", "char"];

export function stateToParams(state) {
  const { tab, parts, textQuery, charQuery, searchDepth, studyScript, sources, selectedId, view } = state;
  const params = new URLSearchParams();

  if (view && view !== "search") {
    params.set("view", view);
    return params;
  }

  if (selectedId) {
    params.set("kanji", selectedId);
  }

  const tabName = TAB_NAMES[tab] || "parts";
  const filledParts = (parts || []).filter((p) => p.trim());
  const hasQuery = tabName === "parts" ? filledParts.length > 0 : tabName === "text" ? textQuery.trim() : charQuery.trim();

  if (hasQuery || !selectedId) {
    // Always record the tab once there's any search context, so a bare reload/share
    // of a search (not just a detail view) lands back on the right form.
    if (hasQuery) params.set("tab", tabName);
    if (tabName === "parts" && filledParts.length) {
      params.set("q", filledParts.join(","));
      if (searchDepth && searchDepth !== 1) params.set("depth", String(searchDepth));
    } else if (tabName === "text" && textQuery.trim()) {
      params.set("q", textQuery.trim());
    } else if (tabName === "char" && charQuery.trim()) {
      params.set("q", charQuery.trim());
    }
  }

  if (studyScript) params.set("script", studyScript);
  if (sources && sources.length) params.set("sources", sources.join(","));

  return params;
}

export function paramsToState(search) {
  const params = new URLSearchParams(search);
  const view = params.get("view");
  if (view) {
    return { view };
  }

  const tabName = params.get("tab");
  const tab = Math.max(0, TAB_NAMES.indexOf(tabName || "parts"));
  const q = params.get("q") || "";
  const depth = parseInt(params.get("depth"), 10);
  const script = params.get("script") || "";
  const sourcesParam = params.get("sources");
  const sources = sourcesParam ? sourcesParam.split(",").filter(Boolean) : null;
  const kanjiId = params.get("kanji") || null;

  return {
    view: "search",
    tab,
    q,
    searchDepth: Number.isFinite(depth) && depth > 0 ? depth : 1,
    studyScript: script,
    sources,
    selectedId: kanjiId,
    hasSearch: Boolean(q) || Boolean(kanjiId),
  };
}

export function paramsToUrl(params) {
  const qs = params.toString();
  return qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
}
