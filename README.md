# Roi-Kham — Thai Word Quiz (Webapp)

A shareable, **anonymous** swipe quiz for Thai words. Send anyone the link — they
play instantly (no nickname, no signup). Words are served from a shared Supabase
database; an admin can grow that word list from a web form + a small script.

```
Browser (index.html)            Supabase (free tier)
  quiz_words  ◄──────────────────  words (62k)
                                   pending_words (admin queue)
admin.html → queue_word_change ─►  pending_words
add_words.py  ─ service role ───►  words   (add / edit / delete)
```

- **No backend server to run.** The browser talks to Supabase directly.
- **Anonymous:** the game starts immediately; scores (⭐ + 🔥 streak) are per-session only — no leaderboard, nothing stored.
- **Plays offline too:** if Supabase is unreachable it falls back to the bundled `words.js`.

## How to play

The card shows a Thai word and a claim; you answer by swiping:

| Swipe | Meaning | Score |
|-------|---------|-------|
| → right | the claim is **true** (ถูก) | +streak (1st +1, 2nd in a row +2, 3rd +3 …) |
| ← left  | the claim is **false** (ผิด) | −1, streak resets |
| ↑ up    | skip (ข้าม) | 0; every 3rd skip −1 |

Three modes (tap the mode button): 🎮 **เกมทายชนิดคำ** (POS) · 🎮 **เกมทายมาตรา**
(final class) · 🎮 **เกมทายคำสะกด** (spelling — wrong spellings are generated on the
fly by swapping same-sound Thai consonants, verified against `words.js`).

---

## One-time setup

### 1. Supabase project + tables
- https://supabase.com → New project (free).
- SQL Editor → run [`schema.sql`](schema.sql) (creates the `words` table).
- SQL Editor → run [`quiz_schema.sql`](quiz_schema.sql) (adds `quiz_words` and the
  `pending_words` admin queue).

### 2. Keys
Dashboard → **Project Settings → API**:

| Value | Used by | Secret? |
|-------|---------|---------|
| Project URL | `index.html`, `admin.html`, `add_words.py` | no |
| `anon` public key | `index.html`, `admin.html` | no (safe in browser) |
| `service_role` key | `add_words.py` only | **YES — keep private** |

### 3. Load the 62k words (one time)
```powershell
$env:SUPABASE_URL = "https://YOURPROJECT.supabase.co"
$env:SUPABASE_SERVICE_KEY = "eyJ...service_role..."
python add_words.py --import          # reads words.js, uploads to Supabase
```

### 4. Connect the apps
Paste your **Project URL** + **anon key** into the CONFIG block near the top of the
`<script>` in **both** `index.html` and `admin.html`.

---

## Growing the word list (admin)

Two ways to add words — both end up in the `words` table via `add_words.py`
(which computes Thai properties with PyThaiNLP). **All writes to `words` happen in
this script (service-role); the browser only enqueues requests.**

```powershell
pip install pythainlp python-crfsuite requests beautifulsoup4 lxml pdfplumber python-docx
# pythainlp+crfsuite: tokenize/POS/syllables · requests+bs4+lxml: URL/HTML
# pdfplumber: PDF · python-docx: Word (PDF/Word libs load only when used)
```

**A. Web form (share this with a helper):** `admin.html` is one self-contained
file with **no password** — give it to anyone you trust and they can **Add / Edit
/ Delete** words. Each action is queued into `pending_words` (it does NOT touch
`words` directly). In the **คิว (queue) tab** you can curate before applying: set a
category on a row or 🗑️ remove junk. Then **you** apply the queue:
```powershell
$env:SUPABASE_URL = "https://YOURPROJECT.supabase.co"
$env:SUPABASE_SERVICE_KEY = "eyJ...service_role..."
python add_words.py --process
```

**B. Direct bulk (script):**
```powershell
python add_words.py --word แมว
python add_words.py --file new_words.txt      # one Thai word per line
```

**C. Harvest from a document or web page:** point the scraper at a URL or a
file; it extracts plain text, tokenizes Thai words, drops any already in the DB
(or already queued), and queues the rest for review (option A):
```powershell
python add_words.py --scrape https://th.wikipedia.org/wiki/แมว
python add_words.py --scrape article.pdf      # also .txt / .html / .docx
```

- **add** → auto-computes `syllables / pos / final_class / live_dead / leading_class` and upserts.
- **edit** → applies only the fields you change.
- **delete** → removes the row.

Newly added words appear in the game automatically (the quiz pulls from Supabase).

### ทายมาตรา uses a syllable table
มาตราตัวสะกด is a per-syllable property, so the ทายมาตรา mode quizzes single
**syllables** (ประจำวัน → ประ / จำ / วัน), drawn from a `syllables` table. Build /
refresh it after adding words:
```powershell
python add_words.py --build-split
```
(New words also add their own syllables automatically when applied.) Offline, the
mode falls back to whole single-syllable words from `words.js`.

> Note: the bundled `words.js` (spelling-check dictionary + offline fallback) is
> NOT updated by `add_words.py`. Freshly added words can rarely cause a false
> result in the spelling mode until `words.js` is regenerated.

---

## Publish the link (all free)

`index.html` is a single static file (plus `words.js`). Drag the folder onto
https://app.netlify.com/drop, or use Vercel / GitHub Pages. The Supabase URL/key
are baked into the file, so anyone who opens the link plays against your database.

`admin.html` has no password (it can only queue word requests, never write to
`words`), so it's safe to send to a trusted helper who adds words for you — you
apply them later with `python add_words.py --process`.

---

## Tuning
- **Words per fetch:** `BUFFER_SIZE` / `REFILL_AT` in `index.html`.
- **Quiz scoring:** `doQuizSwipe()` in `index.html`.
- **Sound effects:** `playSfx()` in `index.html`.

## Files
- `index.html` — the game (share publicly).
- `admin.html` — word add/edit/delete form, no password (share with helpers).
- `add_words.py` — the only script: `--scrape` (URL/doc → queue new words),
  `--process` (apply the queue), `--word` / `--file` (direct add), `--import`
  (bulk load words.js), `--build-split` (build the `syllables` table). Needs the
  service-role key.
- `quiz_schema.sql` — `quiz_words` + `quiz_syllables` + `pending_words` queue + `syllables`.
- `schema.sql` — creates the `words` table.
- `words.js` — bundled word data (offline fallback + spelling dictionary).

## Legacy
The earlier crowd-**verification** game (the `verifications` table and its RPCs in
`schema.sql`) is no longer used. Those objects are harmless if left in place; the
verification UI and its Python scripts have been removed in favor of
admin-controlled word editing.
