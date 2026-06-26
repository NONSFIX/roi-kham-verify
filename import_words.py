#!/usr/bin/env python3
"""
import_words.py
───────────────
Loads the 62k Thai words into your Supabase `words` table.

Source: prototype/words.js (already game-formatted) by default.
Uses only the Python standard library — no pip install needed.

Setup:
  1. Run webapp/schema.sql in the Supabase SQL editor first.
  2. Get your project URL and SERVICE ROLE key:
        Supabase Dashboard → Project Settings → API
     (Use the *service_role* key here — it bypasses RLS for bulk insert.
      Keep it secret; it is NOT the anon key used in index.html.)

Run (PowerShell):
  $env:SUPABASE_URL = "https://YOURPROJECT.supabase.co"
  $env:SUPABASE_SERVICE_KEY = "eyJhbGci...service_role..."
  python import_words.py

Run (bash):
  SUPABASE_URL=https://YOURPROJECT.supabase.co \
  SUPABASE_SERVICE_KEY=eyJ...service_role... \
  python import_words.py

Options:
  --words  path to words.js   (default: ../prototype/words.js)
  --batch  rows per request   (default: 1000)
"""

import os
import re
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# words.js array layout: [syllables, pos, live_dead, final_class,
#                         leading_class, has_sara_a, has_ban_bor, categories]
A_SYL, A_POS, A_LIVE, A_FINAL, A_LEAD, A_SARA, A_BAN, A_CATS = range(8)


def load_words_js(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Could not find a JSON object inside {path}")
    obj = json.loads(text[start:end + 1])
    print(f"Parsed {len(obj):,} words from {path}")
    return obj


def to_rows(word_db: dict) -> list:
    rows = []
    for word, a in word_db.items():
        rows.append({
            "word":          word,
            "syllables":     a[A_SYL]   if len(a) > A_SYL   else None,
            "pos":           a[A_POS]   if len(a) > A_POS   else "",
            "final_class":   a[A_FINAL] if len(a) > A_FINAL else "",
            "live_dead":     a[A_LIVE]  if len(a) > A_LIVE  else "",
            "leading_class": a[A_LEAD]  if len(a) > A_LEAD  else "",
            "categories":    a[A_CATS]  if len(a) > A_CATS  else "",
        })
    return rows


def post_batch(url: str, key: str, rows: list) -> None:
    endpoint = url.rstrip("/") + "/rest/v1/words"
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    # Upsert so re-running is safe
    req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 201, 204):
            raise RuntimeError(f"HTTP {resp.status}: {resp.read().decode()[:300]}")


def main() -> None:
    p = argparse.ArgumentParser(description="Import words.js into Supabase")
    p.add_argument("--words", default=str(Path(__file__).parent.parent / "prototype" / "words.js"))
    p.add_argument("--batch", type=int, default=1000)
    args = p.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables first.")

    rows = to_rows(load_words_js(args.words))
    total = len(rows)
    print(f"Uploading {total:,} rows in batches of {args.batch}...\n")

    sent = 0
    for i in range(0, total, args.batch):
        chunk = rows[i:i + args.batch]
        for attempt in range(1, 4):
            try:
                post_batch(url, key, chunk)
                break
            except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as e:
                detail = ""
                if isinstance(e, urllib.error.HTTPError):
                    detail = e.read().decode(errors="replace")[:300]
                if attempt == 3:
                    sys.exit(f"\nFailed batch at row {i}: {e} {detail}")
                print(f"  retry {attempt} (row {i}): {e} {detail}")
                time.sleep(2 * attempt)
        sent += len(chunk)
        pct = sent / total * 100
        print(f"  {sent:>6,} / {total:,}  ({pct:5.1f}%)")

    print(f"\nDone — {sent:,} words in Supabase.")


if __name__ == "__main__":
    main()
