# How to run the word scraper

`add_words.py --scrape` takes a **web link or a document**, pulls out the plain
text, splits it into Thai words, throws away words you already have, and queues
the new ones for review. You then approve them in `admin.html` and apply them.

```
URL / .txt / .pdf / .docx
        │  extract plain text
        ▼
   tokenize (PyThaiNLP)  →  keep Thai words (length ≥ 2)
        │
        ▼
   drop words already in `words` or already in the queue
        │
        ▼
   queue the NEW words  →  pending_words   (review in admin.html → --process)
```

---

## 1. One-time setup

### a) Install the libraries
```powershell
pip install pythainlp python-crfsuite requests beautifulsoup4 lxml pdfplumber python-docx
```
- `pythainlp` + `python-crfsuite` — tokenize Thai text / compute properties
- `requests` + `beautifulsoup4` + `lxml` — fetch a URL and strip HTML to text
- `pdfplumber` — read PDFs · `python-docx` — read Word `.docx`

> A pip warning like *"pdfplumber.exe ... is not on PATH"* is harmless — the
> script imports these as libraries, not as commands. Verify with:
> ```powershell
> python -c "import pythainlp, requests, bs4, lxml, pdfplumber, docx; print('all good')"
> ```

### b) Set your Supabase keys (every new terminal window)
The scraper writes to your database, so it needs the **service-role** (secret)
key — *not* the anon/publishable key.
```powershell
$env:SUPABASE_URL = "https://qoceonncejbvemcgtwsn.supabase.co"
$env:SUPABASE_SERVICE_KEY = "sb_secret_...your service_role key..."
```
Get it from: Supabase → Project Settings → API keys → **service_role / secret**.
(If you use the anon key by mistake you'll get a `42501 row-level security`
error.)

### c) Make sure the database is ready
Run `schema.sql` and `quiz_schema.sql` once in the Supabase SQL Editor (creates
the `words` and `pending_words` tables). See the main `README.md`.

---

## 2. Run it

Always run from the `roi-kham-verify` folder.

**A web page:**
```powershell
python add_words.py --scrape https://th.wikipedia.org/wiki/แมว
```

**A document on your computer** (PDF / Word / plain text / HTML):
```powershell
python add_words.py --scrape "C:\path\to\article.pdf"
python add_words.py --scrape notes.docx
python add_words.py --scrape words.txt
```
(Quote the path if it contains spaces.)

You'll see a summary like:
```
Extracting text from: https://th.wikipedia.org/wiki/แมว
  4,213 tokens → 968 candidate Thai words
  in DB: 922 · already queued: 5 · NEW: 41
Queued 41 new words → review in admin.html, then: python add_words.py --process
```

---

## 3. Finish: review and apply

1. **Review** — open `admin.html`, go to the **คิว (queue)** tab. For each new
   word you can set a category (optional) or 🗑️ remove junk/names the tokenizer
   picked up.
2. **Apply** — run:
   ```powershell
   python add_words.py --process
   ```
   This computes each word's properties (ชนิดคำ / มาตรา / พยางค์ / ฯลฯ) and writes
   them into `words`. The queued rows flip to `done`.
3. **Refresh the ทายมาตรา data** (so new words appear as syllables in that mode):
   ```powershell
   python add_words.py --build-split
   ```

New words now show up in the game automatically.

---

## 4. Tips & troubleshooting

| Symptom | Cause / fix |
|---|---|
| `42501 ... row-level security` | You used the **anon** key. Set `SUPABASE_SERVICE_KEY` to the **service_role / secret** key. |
| `ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY first` | Env vars not set in this terminal — redo step 1b. |
| `unrecognized arguments: --scrape` | A copy-paste turned `--` into a dash. **Type the two hyphens** yourself. |
| `pip install ...` PATH warning | Harmless, ignore (see step 1a). |
| Lots of junk / names queued | Normal — the tokenizer isn't perfect. That's what the admin **review** step is for. |
| `unauthorized` / 404 on a URL | Some sites block scraping; try a different page or save the text to a `.txt` and scrape that. |
| Re-scraping the same source queues 0 | Correct — those words are already in the DB or queue (dedup working). |

**Good sources for Thai words:** Wikipedia (th.wikipedia.org) articles, news
articles, any Thai `.txt`/PDF/Word document you have.

**Quick reference — all `add_words.py` modes:**
```
--scrape <url|file>   harvest words from a URL or document → queue
--process             apply the review queue into `words`
--build-split         (re)build the syllables table for ทายมาตรา
--word <คำ>            add one word directly
--file <list.txt>     add many words (one per line) directly
--import [words.js]   bulk-load the full words.js into Supabase
```
