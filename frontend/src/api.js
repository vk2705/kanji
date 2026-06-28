const BASE = "http://localhost:8000";

export async function searchByParts(parts) {
  const res = await fetch(`${BASE}/search/parts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function searchByText(q) {
  const res = await fetch(`${BASE}/search/text?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function searchByChar(c) {
  const res = await fetch(`${BASE}/search/char?c=${encodeURIComponent(c)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getKanji(id) {
  const res = await fetch(`${BASE}/kanji/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
