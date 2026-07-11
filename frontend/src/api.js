const BASE = import.meta.env.DEV ? "http://localhost:8000" : "/kanji/api";

async function extractError(res) {
  try {
    const body = await res.json();
    return body.detail || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function searchByParts(parts) {
  const res = await fetch(`${BASE}/search/parts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts }),
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function searchByText(q) {
  const res = await fetch(`${BASE}/search/text?q=${encodeURIComponent(q)}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function searchByChar(c) {
  const res = await fetch(`${BASE}/search/char?c=${encodeURIComponent(c)}`, {
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

export async function register(username, password) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
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
