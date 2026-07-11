const BASE = import.meta.env.DEV ? "http://localhost:8000" : "/kanji/api";

async function extractError(res) {
  try {
    const body = await res.json();
    return body.detail || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function searchByParts(parts, script = null) {
  const res = await fetch(`${BASE}/search/parts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts, script }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function searchByText(q, script = null) {
  const params = new URLSearchParams({ q });
  if (script) params.set("script", script);
  const res = await fetch(`${BASE}/search/text?${params}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function searchByChar(c, script = null) {
  const params = new URLSearchParams({ c });
  if (script) params.set("script", script);
  const res = await fetch(`${BASE}/search/char?${params}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function getKanji(id) {
  const res = await fetch(`${BASE}/kanji/${encodeURIComponent(id)}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function register(username, password, prefs = {}) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, ...prefs }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function logout() {
  const res = await fetch(`${BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function updatePreferences(prefs) {
  const res = await fetch(`${BASE}/auth/preferences`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prefs),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function addAlias(kanjiId, alias, visibility = "private") {
  const res = await fetch(`${BASE}/aliases`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kanji_id: kanjiId, alias, visibility }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function addStory(kanjiId, story, visibility = "private") {
  const res = await fetch(`${BASE}/stories`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kanji_id: kanjiId, story, visibility }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}
