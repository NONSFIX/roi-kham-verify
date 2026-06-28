#!/usr/bin/env python3
"""
add_words.py
────────────
Add / edit / delete Thai words in the Supabase `words` table.

Two ways to use it:

  1. Process the admin queue (words submitted from admin.html):
         python add_words.py --process

  2. Bulk-add directly (a human-maintained list, no web form):
         python add_words.py --word แมว
         python add_words.py --file new_words.txt      # one Thai word per line

For 'add' it auto-computes the linguistic properties (syllables, pos,
final_class, live_dead, leading_class) with PyThaiNLP — the SAME logic the
original words.db was built with (Handoff/build_word_db.py). 'edit' applies only
the fields you override; 'delete' removes the row.

Setup:
  pip install pythainlp python-crfsuite      # crfsuite is needed for POS tagging
  $env:SUPABASE_URL        = "https://YOURPROJECT.supabase.co"
  $env:SUPABASE_SERVICE_KEY = "eyJ...service_role..."   # NOT the anon key
"""

import os
import re
import sys
import json
import argparse
import datetime
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# Print Thai correctly on Windows consoles (cp1252 → utf-8)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Thai property derivation (mirrors Handoff/build_word_db.py) ───────────────
MID_CLASS  = set("กจดตบปอ")
HIGH_CLASS = set("ขฃฉฐถผฝศษสห")
FINAL_CLASS_MAP = {
    **{c: "กก"  for c in "กขคฆ"},
    **{c: "กด"  for c in "จชซฌฎฏฐฑฒดตถทธศษส"},
    **{c: "กบ"  for c in "บปพฟภ"},
    "ง": "กง",
    **{c: "กน"  for c in "ญณนรลฬ"},
    "ม": "กม", "ย": "เกย", "ว": "เกอว",
}
ORCHID_POS_MAP = {
    "NCMN": "NOUN", "NTTL": "NOUN", "NONM": "NOUN", "NCNM": "NOUN",
    "VACT": "VERB", "VSTA": "VERB", "VMODX": "VERB",
    "ADVN": "ADV", "ADVI": "ADV", "ADVP": "ADV",
    "ADJV": "ADJ", "ATTQ": "ADJ",
    "RPRE": "PREP", "RPST": "PREP",
    "JCRR": "CONJ", "JCMP": "CONJ", "JSBR": "CONJ",
    "PPRS": "PRON", "PDMT": "PRON", "PNTR": "PRON",
    "INTJ": "INTJ",
}
_STOPS = set("กขคฆจชซฌฎฏฐฑฒดตถทธศษสบปพฟภ")


def _lead_class(word: str) -> str:
    for ch in word:
        if "ก" <= ch <= "๎":
            if ch in MID_CLASS:  return "mid"
            if ch in HIGH_CLASS: return "high"
            return "low"
    return ""


def _final_class(word: str) -> str:
    cons = [ch for ch in word if "ก" <= ch <= "ฮ"]
    if not cons:
        return "none"
    return FINAL_CLASS_MAP.get(cons[-1], "none")


def _live_dead(word: str) -> str:
    cons = [ch for ch in word if "ก" <= ch <= "ฮ"]
    if not cons:
        return "unknown"
    return "dead" if cons[-1] in _STOPS else "live"


# Syllable-aware มาตราตัวสะกด (better than last-consonant for the quiz):
# handles open syllables, ำ (sara am → ม), การันต์, and leading-vowel finals.
_TONE_MARKS = set("่้๊๋")            # 0E48–0E4B
_VOWEL_END = set("ะัาๅๆิีึืฺุู็")   # following/above/below vowel signs


def _syll_final_class(syl: str) -> str:
    s = "".join(c for c in syl if c not in _TONE_MARKS)
    if not s or "์" in s:            # การันต์ → silent, treat as no ตัวสะกด
        return "none"
    last = s[-1]
    if last == "ำ":                  # sara am = vowel + final /m/
        return "กม"
    if last in _VOWEL_END:           # ends in a vowel sign → open syllable
        return "none"
    if "ก" <= last <= "ฮ":           # ends in a consonant
        cons = [c for c in s if "ก" <= c <= "ฮ"]
        # a real ตัวสะกด needs an initial consonant before it; a lone consonant
        # after a leading vowel (ไฟ, โต) is the initial, so the syllable is open
        return FINAL_CLASS_MAP.get(cons[-1], "none") if len(cons) >= 2 else "none"
    return "none"


_PYTHAINLP = None


def _load_pythainlp():
    global _PYTHAINLP
    if _PYTHAINLP is None:
        try:
            from pythainlp.tokenize import syllable_tokenize
            from pythainlp.tag import pos_tag
            _PYTHAINLP = (syllable_tokenize, pos_tag)
        except ImportError:
            sys.exit("ERROR: PyThaiNLP is required to compute properties.\n"
                     "  pip install pythainlp")
    return _PYTHAINLP


_WARNED = set()


def _warn_once(key: str, msg: str):
    if key not in _WARNED:
        print(f"  ! {msg}", file=sys.stderr)
        _WARNED.add(key)


def derive_row(word: str) -> dict:
    """Raw Thai word → full Supabase `words` row (categories left blank).

    syllables/pos use PyThaiNLP (which needs `python-crfsuite`). If that isn't
    installed they degrade gracefully (syllables=1, pos='') with a one-time
    warning — you can still set them via overrides in the admin form.
    """
    syllable_tokenize, pos_tag = _load_pythainlp()
    try:
        syls = len(syllable_tokenize(word))
    except Exception as e:  # noqa: BLE001
        _warn_once("syl", f"syllable tokenizer unavailable ({e}); syllables=1. "
                          "Fix: pip install python-crfsuite")
        syls = 1
    try:
        tagged = pos_tag([word], corpus="orchid")
        pos = ORCHID_POS_MAP.get(tagged[0][1], "") if tagged else ""
    except Exception as e:  # noqa: BLE001
        _warn_once("pos", f"POS tagger unavailable ({e}); pos left blank. "
                          "Fix: pip install python-crfsuite")
        pos = ""
    return {
        "word": word,
        "syllables": syls,
        "pos": pos,
        "final_class": _final_class(word),
        "live_dead": _live_dead(word),
        "leading_class": _lead_class(word),
        "categories": "",
    }


# ── Supabase REST (service-role; bypasses RLS) ───────────────────────────────
URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def _request(method: str, path: str, body=None, prefer=None):
    if not URL or not KEY:
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(URL + "/rest/v1" + path, data=data, method=method)
    req.add_header("apikey", KEY)
    req.add_header("Authorization", f"Bearer {KEY}")
    req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt.strip() else None)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")


def upsert_word(row: dict):
    _request("POST", "/words", [row], prefer="resolution=merge-duplicates,return=minimal")


def get_word(word: str):
    _, data = _request("GET", f"/words?word=eq.{urllib.parse.quote(word)}&select=*")
    return data[0] if data else None


def delete_word(word: str):
    _request("DELETE", f"/words?word=eq.{urllib.parse.quote(word)}", prefer="return=minimal")


def get_pending():
    _, data = _request("GET", "/pending_words?status=eq.pending&order=id&select=*")
    return data or []


def mark_pending(pid: int, status: str, result: str):
    _request("PATCH", f"/pending_words?id=eq.{pid}",
             {"status": status, "result": result,
              "processed_at": datetime.datetime.utcnow().isoformat()},
             prefer="return=minimal")


# ── Syllables (for the ทายมาตรา quiz) ────────────────────────────────────────
THAI_RE = re.compile(r"^[ก-๛]+$")


def _syllables(word: str) -> list:
    """Split a word into syllables (PyThaiNLP); fall back to [word]."""
    syllable_tokenize, _ = _load_pythainlp()
    try:
        return [s.strip() for s in syllable_tokenize(word) if s and s.strip()]
    except Exception:  # noqa: BLE001
        return [word]


def upsert_syllables(words: list) -> int:
    """Tokenize words into syllables and upsert each (+ its final_class)."""
    seen = {}
    for w in words:
        for s in _syllables(w):
            if len(s) >= 2 and THAI_RE.match(s):
                seen[s] = _syll_final_class(s)
    rows = [{"syllable": s, "final_class": fc} for s, fc in seen.items()]
    for i in range(0, len(rows), 500):
        _request("POST", "/syllables", rows[i:i + 500],
                 prefer="resolution=merge-duplicates,return=minimal")
    return len(rows)


# ── Actions ──────────────────────────────────────────────────────────────────
def apply_add(word: str, overrides: dict | None) -> str:
    row = derive_row(word)
    if overrides:
        row.update({k: v for k, v in overrides.items() if k in row})
    upsert_word(row)
    try:
        upsert_syllables([word])     # keep the syllable table current (optional)
    except Exception:                # noqa: BLE001  (table may not exist yet)
        pass
    return f"added pos={row['pos']} final={row['final_class']} live_dead={row['live_dead']}"


def apply_edit(word: str, overrides: dict | None) -> str:
    existing = get_word(word)
    if existing:
        existing.update(overrides or {})
        # keep only known columns
        row = {k: existing.get(k) for k in
               ("word", "syllables", "pos", "final_class", "live_dead", "leading_class", "categories")}
        row["word"] = word
    else:
        row = derive_row(word)
        if overrides:
            row.update({k: v for k, v in overrides.items() if k in row})
    upsert_word(row)
    return "edited"


def apply_delete(word: str) -> str:
    delete_word(word)
    return "deleted"


def run_action(action: str, word: str, overrides: dict | None) -> str:
    if action == "add":
        return apply_add(word, overrides)
    if action == "edit":
        return apply_edit(word, overrides)
    if action == "delete":
        return apply_delete(word)
    raise ValueError(f"unknown action: {action}")


def process_queue() -> None:
    pending = get_pending()
    if not pending:
        print("Queue empty — nothing to process.")
        return
    print(f"Processing {len(pending)} queued request(s)...")
    ok = err = 0
    for r in pending:
        word, action = r["word"], r.get("action", "add")
        try:
            msg = run_action(action, word, r.get("overrides"))
            mark_pending(r["id"], "done", msg)
            print(f"  ✓ {action:6} {word} — {msg}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            mark_pending(r["id"], "error", str(e)[:300])
            print(f"  ✗ {action:6} {word} — {e}")
            err += 1
    print(f"\nDone — {ok} applied, {err} error(s).")


def bulk_add(words: list[str]) -> None:
    words = [w.strip() for w in words if w.strip()]
    print(f"Adding {len(words)} word(s) directly...")
    ok = err = 0
    for w in words:
        try:
            msg = apply_add(w, None)
            print(f"  ✓ {w} — {msg}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {w} — {e}")
            err += 1
    print(f"\nDone — {ok} added, {err} error(s).")


# ── Bulk import from a words.js file (folds in the old import_words.py) ───────
# words.js layout: [syllables, pos, live_dead, final_class, leading_class,
#                   has_sara_a, has_ban_bor, categories]
def load_words_js(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        sys.exit(f"Could not find a JSON object in {path}")
    return json.loads(text[s:e + 1])


def rows_from_words_js(db: dict) -> list:
    rows = []
    for word, a in db.items():
        rows.append({
            "word": word,
            "syllables":     a[0] if len(a) > 0 else None,
            "pos":           a[1] if len(a) > 1 else "",
            "live_dead":     a[2] if len(a) > 2 else "",
            "final_class":   a[3] if len(a) > 3 else "",
            "leading_class": a[4] if len(a) > 4 else "",
            "categories":    a[7] if len(a) > 7 else "",
        })
    return rows


def import_words_js(path: str, batch: int = 1000) -> None:
    rows = rows_from_words_js(load_words_js(path))
    total = len(rows)
    print(f"Importing {total:,} words from {path} (batches of {batch})...")
    sent = 0
    for i in range(0, total, batch):
        chunk = rows[i:i + batch]
        _request("POST", "/words", chunk, prefer="resolution=merge-duplicates,return=minimal")
        sent += len(chunk)
        print(f"  {sent:>6,}/{total:,}")
    print(f"Done — {sent:,} words upserted.")


# ── Ingestion: URL / document → text → tokens → dedup → queue ────────────────
def extract_text(src: str) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        return _text_from_url(src)
    ext = Path(src).suffix.lower()
    if ext == ".txt":
        return Path(src).read_text(encoding="utf-8", errors="replace")
    if ext in (".html", ".htm"):
        return _html_to_text(Path(src).read_text(encoding="utf-8", errors="replace"))
    if ext == ".pdf":
        return _text_from_pdf(src)
    if ext == ".docx":
        return _text_from_docx(src)
    sys.exit(f"Unsupported source: {src}  (use a URL, .txt, .html, .pdf, or .docx)")


def _text_from_url(url: str) -> str:
    try:
        import requests
    except ImportError:
        sys.exit("pip install requests beautifulsoup4 lxml")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (RoiKham ingest)"}, timeout=30)
    r.raise_for_status()
    return _html_to_text(r.text)


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("pip install beautifulsoup4 lxml")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def _text_from_pdf(path: str) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pip install pdfplumber")
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _text_from_docx(path: str) -> str:
    try:
        import docx
    except ImportError:
        sys.exit("pip install python-docx")
    return "\n".join(p.text for p in docx.Document(path).paragraphs)


def _existing_in(table: str, col: str, words: list, chunk: int = 80) -> set:
    """Return which of `words` already exist in a table (batched PostgREST in.())."""
    found = set()
    for i in range(0, len(words), chunk):
        part = words[i:i + chunk]
        inlist = ",".join('"' + w + '"' for w in part)
        q = urllib.parse.quote(inlist, safe='",')   # keep " and , literal, encode Thai
        _, data = _request("GET", f"/{table}?{col}=in.({q})&select={col}")
        for row in (data or []):
            found.add(row[col])
    return found


def scrape(src: str) -> None:
    print(f"Extracting text from: {src}")
    text = extract_text(src)
    from pythainlp.tokenize import word_tokenize
    toks = word_tokenize(text, engine="newmm")
    seen, candidates = set(), []
    for t in toks:
        t = t.strip()
        if len(t) >= 2 and THAI_RE.match(t) and t not in seen:
            seen.add(t)
            candidates.append(t)
    print(f"  {len(toks):,} tokens → {len(candidates):,} candidate Thai words")
    if not candidates:
        print("No Thai words found.")
        return
    have_words = _existing_in("words", "word", candidates)
    have_pending = _existing_in("pending_words", "word", candidates)
    new = [w for w in candidates if w not in have_words and w not in have_pending]
    print(f"  in DB: {len(have_words):,} · already queued: {len(have_pending - have_words):,} · NEW: {len(new):,}")
    if not new:
        print("Nothing new to queue.")
        return
    rows = [{"action": "add", "word": w, "note": f"scraped: {src[:80]}"} for w in new]
    for i in range(0, len(rows), 200):
        _request("POST", "/pending_words", rows[i:i + 200], prefer="return=minimal")
    print(f"Queued {len(new):,} new words → review in admin.html, then: python add_words.py --process")


# ── Build the syllables table for the ทายมาตรา quiz ──────────────────────────
def fetch_all_words(page: int = 1000) -> list:
    out, offset = [], 0
    while True:
        _, data = _request("GET", f"/words?select=word&order=word&limit={page}&offset={offset}")
        if not data:
            break
        out.extend(r["word"] for r in data)
        if len(data) < page:
            break
        offset += page
    return out


def build_split() -> None:
    print("Reading words from Supabase...")
    words = fetch_all_words()
    print(f"  {len(words):,} words → tokenizing into syllables...")
    syl = {}
    for w in words:
        for s in _syllables(w):
            if len(s) >= 2 and THAI_RE.match(s):
                syl[s] = _syll_final_class(s)
    rows = [{"syllable": s, "final_class": fc} for s, fc in syl.items()]
    print(f"  {len(rows):,} distinct syllables → upserting into `syllables`...")
    sent = 0
    for i in range(0, len(rows), 1000):
        chunk = rows[i:i + 1000]
        _request("POST", "/syllables", chunk, prefer="resolution=merge-duplicates,return=minimal")
        sent += len(chunk)
        print(f"  {sent:,}/{len(rows):,}")
    print(f"Done — {len(rows):,} syllables.")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Manage Thai words in Supabase (scrape / add / edit / delete / queue / bulk-import / build-split)")
    p.add_argument("--process", action="store_true", help="apply the admin queue (pending_words)")
    p.add_argument("--word", help="add a single word directly")
    p.add_argument("--file", help="add words from a text file (one Thai word per line)")
    p.add_argument("--scrape", metavar="URL_OR_FILE",
                   help="extract text from a URL/.txt/.html/.pdf/.docx, tokenize, drop known words, queue the rest")
    p.add_argument("--build-split", dest="build_split", action="store_true",
                   help="(re)build the `syllables` table used by the ทายมาตรา quiz")
    p.add_argument("--import", dest="do_import", nargs="?", const="words.js", metavar="WORDS_JS",
                   help="bulk-import every word from a words.js file (default: words.js)")
    args = p.parse_args()

    if args.scrape:
        scrape(args.scrape)
    elif args.build_split:
        build_split()
    elif args.do_import is not None:
        import_words_js(args.do_import)
    elif args.word:
        bulk_add([args.word])
    elif args.file:
        bulk_add(Path(args.file).read_text(encoding="utf-8").splitlines())
    else:
        # default action is to apply the queue
        process_queue()


if __name__ == "__main__":
    main()
