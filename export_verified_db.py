#!/usr/bin/env python3
"""
export_verified_db.py
─────────────────────
Pulls every crowd vote from the Supabase `verifications` table and bakes the
results into a NEW copy of words.db — so you get a fresh, hand-offable database
file with the verification columns filled in.

This is the Supabase version of the old import_verifications.py (which read a
local verifications.json). Same column layout, so anything downstream that read
the old words.db still works.

Uses only the Python standard library — no pip install needed.

What it writes (columns are added to a COPY of words.db if missing):
    pos_verified        INTEGER   pos_correction        TEXT   pos_wrong        INTEGER
    final_verified      INTEGER   final_correction      TEXT   final_wrong      INTEGER
    livedead_verified   INTEGER   livedead_correction   TEXT   livedead_wrong   INTEGER
    lead_verified       INTEGER   lead_correction       TEXT   lead_wrong       INTEGER
    cats_verified       INTEGER   cats_correction       TEXT   cats_wrong       INTEGER

  *_verified   = how many players voted "correct" for that word+field
  *_wrong      = how many voted "wrong"
  *_correction = the MOST common fix players suggested (majority wins)

The script always starts from a clean copy of the source words.db, so re-running
it is safe and idempotent — it never double-counts.

Get your keys: Supabase Dashboard → Project Settings → API.
Use the *service_role* key (it bypasses RLS so the script can READ raw votes —
the anon key only has INSERT). Keep it secret.

Run (PowerShell):
  $env:SUPABASE_URL = "https://YOURPROJECT.supabase.co"
  $env:SUPABASE_SERVICE_KEY = "eyJhbGci...service_role..."
  python export_verified_db.py

Run (bash):
  SUPABASE_URL=https://YOURPROJECT.supabase.co \
  SUPABASE_SERVICE_KEY=eyJ...service_role... \
  python export_verified_db.py

Options:
  --db    source words.db   (default: ../roi-kham-cardgame/Handoff/words.db)
  --out   new db to write   (default: words_verified.db, next to this script)
  --page  rows per request  (default: 1000, Supabase max)
"""

import os
import sys
import json
import shutil
import sqlite3
import argparse
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from collections import Counter, defaultdict

# field key  →  (verified_col,      correction_col,      wrong_col,        label)
FIELD_COLUMNS = {
    "pos":           ("pos_verified",      "pos_correction",      "pos_wrong",      "ชนิดคำ (POS)"),
    "final_class":   ("final_verified",    "final_correction",    "final_wrong",    "มาตราตัวสะกด"),
    "live_dead":     ("livedead_verified", "livedead_correction", "livedead_wrong", "เสียงคำ (Live/Dead)"),
    "leading_class": ("lead_verified",     "lead_correction",     "lead_wrong",     "อักษร 3 หมู่"),
    "categories":    ("cats_verified",     "cats_correction",     "cats_wrong",     "หมวดหมู่คำ (Semantic)"),
}
VALID_VOTES = {"correct", "wrong"}


def fetch_all_verifications(url: str, key: str, page: int) -> list:
    """Page through the verifications table via the Supabase REST API."""
    base = url.rstrip("/") + "/rest/v1/verifications"
    query = urllib.parse.urlencode({
        "select": "word,field,vote,correction",
        "order": "id",
    })
    rows = []
    offset = 0
    while True:
        req = urllib.request.Request(f"{base}?{query}&limit={page}&offset={offset}")
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            sys.exit(f"\nSupabase read failed (HTTP {e.code}): {detail}\n"
                     f"Check your SUPABASE_URL and that the key is the service_role key.")
        except urllib.error.URLError as e:
            sys.exit(f"\nCould not reach Supabase: {e}")
        rows.extend(batch)
        print(f"  fetched {len(rows):,} votes...")
        if len(batch) < page:
            break
        offset += page
    return rows


def aggregate(records: list) -> dict:
    """Collapse raw votes into per-(field, word) tallies."""
    # agg[field][word] = {"correct": int, "wrong": int, "fixes": Counter}
    agg = {f: defaultdict(lambda: {"correct": 0, "wrong": 0, "fixes": Counter()})
           for f in FIELD_COLUMNS}
    skipped = invalid = 0

    for rec in records:
        word = rec.get("word")
        field = rec.get("field")
        vote = rec.get("vote")
        correction = rec.get("correction")

        if not word or field not in FIELD_COLUMNS:
            invalid += 1
            continue
        if vote not in VALID_VOTES:
            skipped += 1
            continue

        cell = agg[field][word]
        if vote == "correct":
            cell["correct"] += 1
        else:  # wrong
            cell["wrong"] += 1
            if correction:
                if isinstance(correction, list):
                    correction = ",".join(sorted(correction))
                cell["fixes"][str(correction)] += 1

    return {"agg": agg, "skipped": skipped, "invalid": invalid}


def ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(words)")}
    added = []
    for ver_col, cor_col, wrong_col, _ in FIELD_COLUMNS.values():
        for col, defn in [(ver_col, "INTEGER DEFAULT 0"),
                          (wrong_col, "INTEGER DEFAULT 0"),
                          (cor_col, "TEXT DEFAULT ''")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE words ADD COLUMN {col} {defn}")
                added.append(col)
    conn.commit()
    print(f"  Columns ready ({len(added)} added)." if added
          else "  All verification columns already present.")


def apply_to_db(out_db: str, data: dict) -> dict:
    conn = sqlite3.connect(out_db)
    ensure_columns(conn)

    stats = {f: {"correct": 0, "wrong": 0} for f in FIELD_COLUMNS}
    stats["not_found"] = 0

    known = {row[0] for row in conn.execute("SELECT word FROM words")}

    for field, (ver_col, cor_col, wrong_col, _) in FIELD_COLUMNS.items():
        for word, cell in data["agg"][field].items():
            if word not in known:
                stats["not_found"] += 1
                continue
            fix = cell["fixes"].most_common(1)[0][0] if cell["fixes"] else ""
            conn.execute(
                f"UPDATE words SET {ver_col} = ?, {wrong_col} = ?, {cor_col} = ? "
                f"WHERE word = ?",
                (cell["correct"], cell["wrong"], fix, word),
            )
            stats[field]["correct"] += cell["correct"]
            stats[field]["wrong"] += cell["wrong"]

    conn.commit()
    conn.close()
    return stats


def main() -> None:
    here = Path(__file__).parent
    p = argparse.ArgumentParser(description="Bake Supabase votes into a fresh words.db")
    p.add_argument("--db",   default=str(here.parent / "roi-kham-cardgame" / "Handoff" / "words.db"),
                   help="source words.db to copy from")
    p.add_argument("--out",  default=str(here / "words_verified.db"),
                   help="path of the new database file to write")
    p.add_argument("--page", type=int, default=1000, help="rows per Supabase request")
    args = p.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables first.")

    src = Path(args.db)
    if not src.exists():
        sys.exit(f"ERROR: source database not found: {src}")

    print(f"Source DB : {src}")
    print(f"Output DB : {args.out}\n")

    print("Downloading votes from Supabase...")
    records = fetch_all_verifications(url, key, args.page)
    print(f"Total votes: {len(records):,}\n")

    data = aggregate(records)

    # Fresh copy every run → idempotent, original untouched.
    shutil.copyfile(src, args.out)
    print("Writing verified database...")
    stats = apply_to_db(args.out, data)

    print("\nResults:")
    total = 0
    for field, (_, _, _, label) in FIELD_COLUMNS.items():
        c, w = stats[field]["correct"], stats[field]["wrong"]
        total += c + w
        print(f"  {label:<22}  ✓ confirmed: {c:>6,}   ✗ corrected: {w:>6,}")
    print(f"  {'─' * 52}")
    print(f"  Skipped (no/blank vote) : {data['skipped']:>6,}")
    print(f"  Invalid records         : {data['invalid']:>6,}")
    print(f"  Votes for unknown words : {stats['not_found']:>6,}")
    print(f"\nDone — {total:,} votes baked into {args.out}")


if __name__ == "__main__":
    main()
