const BASE = import.meta.env.DEV ? "http://localhost:8000" : "/kanji/api";

// kanji.image_url from the API is a server-relative path (e.g. "/uploads/usr17.png");
// resolve it against BASE the same way every other endpoint is addressed.
export function resolveImageUrl(imageUrl) {
  return imageUrl ? `${BASE}${imageUrl}` : null;
}

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

export async function googleLogin(credential, prefs = {}) {
  const res = await fetch(`${BASE}/auth/google`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential, ...prefs }),
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

export async function createKanji({ keyword, character = null, script = "ja-kanji", visibility = "private" }) {
  const res = await fetch(`${BASE}/kanji`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keyword, character, script, visibility }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function createDecomposition(kanjiId, { parts, label = null, visibility = "private" }) {
  const res = await fetch(`${BASE}/kanji/${encodeURIComponent(kanjiId)}/decompositions`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts, label, visibility }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function uploadKanjiImage(kanjiId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE}/kanji/${encodeURIComponent(kanjiId)}/image`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function getMyContributions() {
  const res = await fetch(`${BASE}/me/contributions`, { credentials: "include" });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function setKanjiVisibility(kanjiId, visibility) {
  const res = await fetch(`${BASE}/kanji/${encodeURIComponent(kanjiId)}/visibility`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visibility }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function setRowVisibility(table, rowId, visibility) {
  const res = await fetch(`${BASE}/${table}/${rowId}/visibility`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visibility }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}
