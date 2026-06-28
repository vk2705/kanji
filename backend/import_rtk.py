"""
import_rtk.py — Generate data.txt entries from kanjidic2 + KRADFILE.

Usage:
    python3 import_rtk.py [--kanjidic2 /path/to/kanjidic2.xml.gz] [--kradfile /path/to/kradfile.gz] [--out data.txt]

Downloads kanjidic2.xml.gz and kradfile.gz if paths not given.
Appends new rtk{frame} entries to data.txt (skips entries already present).
"""

import argparse
import gzip
import sys
import os
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

KANJIDIC2_URL = "http://ftp.edrdg.org/pub/Nihongo/kanjidic2.xml.gz"
KRADFILE_URL  = "http://ftp.edrdg.org/pub/Nihongo/kradfile.gz"

DATA_TXT = Path(__file__).parent / "data.txt"


def download(url: str, dest: Path):
    print(f"Downloading {url} ...", flush=True)
    urllib.request.urlretrieve(url, dest)
    print(f"  → saved to {dest}", flush=True)


def load_kanjidic2(path: Path) -> dict[str, tuple[int, str]]:
    """Returns {char: (heisig6_frame, first_english_meaning)}."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as f:
        data = f.read()
    root = ET.fromstring(data)
    result = {}
    for c in root.findall("character"):
        h6 = c.find('.//dic_ref[@dr_type="heisig6"]')
        if h6 is None:
            continue
        lit = c.find("literal").text
        frame = int(h6.text)
        meanings = [m.text for m in c.findall(".//meaning") if m.get("m_lang") is None]
        keyword = meanings[0] if meanings else lit
        result[lit] = (frame, keyword)
    return result


def load_kradfile(path: Path) -> dict[str, list[str]]:
    """Returns {char: [component_chars]} from KRADFILE (EUC-JP encoded)."""
    opener = gzip.open if str(path).endswith(".gz") else open
    result = {}
    with opener(path, "rb") as f:
        for raw in f:
            try:
                line = raw.decode("euc-jp").strip()
            except UnicodeDecodeError:
                continue
            if not line or line.startswith("#"):
                continue
            parts = line.split(" : ", 1)
            if len(parts) != 2:
                continue
            char = parts[0].strip()
            components = [c.strip() for c in parts[1].split() if c.strip()]
            result[char] = components
    return result


def load_existing_ids(data_txt: Path) -> set[str]:
    """Return set of IDs already in data.txt."""
    ids = set()
    if not data_txt.exists():
        return ids
    with open(data_txt, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entry_id = line.split(":")[0].strip().lower()
            if entry_id:
                ids.add(entry_id)
    return ids


def load_existing_chars(data_txt: Path) -> set[str]:
    """Return set of kanji characters already assigned in data.txt."""
    chars = set()
    if not data_txt.exists():
        return chars
    with open(data_txt, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) >= 2:
                ch = parts[1].strip()
                if ch and ch not in ("?", "??"):
                    chars.add(ch)
    return chars


def sanitize_keyword(keyword: str) -> str:
    """Lowercase and strip, remove commas."""
    return keyword.lower().replace(",", " ").strip()


def main():
    parser = argparse.ArgumentParser(description="Generate RTK entries for data.txt")
    parser.add_argument("--kanjidic2", type=Path, default=None)
    parser.add_argument("--kradfile",  type=Path, default=None)
    parser.add_argument("--out",       type=Path, default=DATA_TXT)
    parser.add_argument("--dry-run",   action="store_true", help="Print entries instead of writing")
    args = parser.parse_args()

    # Resolve or download kanjidic2
    kanjidic2_path = args.kanjidic2
    if kanjidic2_path is None:
        kanjidic2_path = Path("/tmp/kanjidic2.xml.gz")
        if not kanjidic2_path.exists():
            download(KANJIDIC2_URL, kanjidic2_path)

    kradfile_path = args.kradfile
    if kradfile_path is None:
        kradfile_path = Path("/tmp/kradfile.gz")
        if not kradfile_path.exists():
            download(KRADFILE_URL, kradfile_path)

    print("Loading kanjidic2...", flush=True)
    kd2 = load_kanjidic2(kanjidic2_path)
    print(f"  {len(kd2)} RTK6 entries", flush=True)

    print("Loading KRADFILE...", flush=True)
    krad = load_kradfile(kradfile_path)
    print(f"  {len(krad)} entries", flush=True)

    existing_ids   = load_existing_ids(args.out)
    existing_chars = load_existing_chars(args.out)

    new_lines = []
    skipped = 0
    for char, (frame, keyword) in sorted(kd2.items(), key=lambda x: x[1][0]):
        entry_id = f"rtk{frame}"
        if entry_id in existing_ids:
            skipped += 1
            continue
        if char in existing_chars:
            skipped += 1
            continue

        keyword_clean = sanitize_keyword(keyword)
        components = krad.get(char, [])
        # Filter out the character itself as its own component
        components = [c for c in components if c != char]
        parts_str = ",".join(components)

        line = f"{entry_id}:{char}:{keyword_clean}:{parts_str}"
        new_lines.append(line)

    print(f"  {len(new_lines)} new entries, {skipped} already present", flush=True)

    if args.dry_run:
        for line in new_lines[:50]:
            print(line)
        if len(new_lines) > 50:
            print(f"  ... and {len(new_lines) - 50} more")
        return

    with open(args.out, "a", encoding="utf-8") as f:
        f.write("\n# --- Imported from kanjidic2 + KRADFILE ---\n")
        for line in new_lines:
            f.write(line + "\n")

    print(f"Written {len(new_lines)} entries to {args.out}", flush=True)
    print("Run /admin/reimport endpoint (or restart backend) to rebuild the database.", flush=True)


if __name__ == "__main__":
    main()
