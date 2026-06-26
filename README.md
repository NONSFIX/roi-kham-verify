# Roi-Kham Word Verification — Webapp

A shareable web game. Send anyone the link, they pick a verification mode and
swipe through Thai words. Every vote flows into one shared Supabase database.

```
Browser (index.html)            Supabase (free tier)
  swipe → insert vote   ───────►  verifications  table
  get_words / stats     ◄───────  words (62k) + RPC functions
```

- **No backend server to run.** The browser talks to Supabase directly.
- **Least-voted-first:** the server hands out the words that need votes most.
- **Nickname, no signup:** players type a name once → leaderboard.
- A word stops appearing once it has **3 votes** (`VOTES_NEEDED`).

---

## One-time setup (~15 min)

### 1. Create a Supabase project
- Go to https://supabase.com → New project (free).
- Wait for it to finish provisioning.

### 2. Create the database
- Dashboard → **SQL Editor** → New query.
- Paste the entire contents of [`schema.sql`](schema.sql) → **Run**.
- This creates the `words` + `verifications` tables, security rules, and the
  `get_words`, `field_stats`, `leaderboard` functions.

### 3. Get your keys
- Dashboard → **Project Settings → API**. You need three values:
  | Value | Used by | Secret? |
  |-------|---------|---------|
  | Project URL | both | no |
  | `anon` public key | `index.html` | no (safe in browser) |
  | `service_role` key | `import_words.py` | **YES — keep private** |

### 4. Load the 62k words
From this `webapp/` folder, in **PowerShell**:
```powershell
$env:SUPABASE_URL = "https://YOURPROJECT.supabase.co"
$env:SUPABASE_SERVICE_KEY = "eyJhbGci...service_role..."
python import_words.py
```
It reads `../prototype/words.js` and uploads in batches (~1 min). Re-running is
safe (it upserts).

### 5. Connect the game
- Open [`index.html`](index.html), find the **CONFIG** block near the top of the
  `<script>`, and paste your **Project URL** and **anon** key:
  ```js
  const SUPABASE_URL      = 'https://YOURPROJECT.supabase.co';
  const SUPABASE_ANON_KEY = 'eyJhbGci...anon...';
  ```
- Open `index.html` in a browser to test locally. Type a nickname, swipe a few
  words, then check **Supabase → Table editor → verifications** — your votes
  should appear.

---

## Publish the link (pick one, all free)

`index.html` is a single static file, so any static host works.

**Netlify Drop (easiest):**
1. Go to https://app.netlify.com/drop
2. Drag the `webapp` folder onto the page.
3. You get a public URL like `https://roi-kham-xxx.netlify.app` — share it.

**Vercel:** `npm i -g vercel` → run `vercel` inside `webapp/`.

**GitHub Pages:** push `webapp/` to a repo → Settings → Pages → deploy from branch.

> Re-deploy whenever you change `index.html`. The Supabase URL/key are baked into
> the file, so anyone who opens the link plays against your shared database.

---

## How play works

| Swipe | Meaning | Score |
|-------|---------|-------|
| → right | the shown answer is **correct** | +10 |
| ← left  | **wrong** → pick the correct answer | +20 |
| ↑ up    | skip (no vote recorded) | — |

5 verification modes (tap the mode button in the header):
📝 ชนิดคำ · 🔤 มาตราตัวสะกด · 🔊 เสียงคำ · 🎯 อักษร 3 หมู่ · 🏷️ หมวดหมู่คำ (multi-select).

---

## Reading the results

In the Supabase SQL editor:

```sql
-- Words the crowd disagrees with the database on (POS example)
select word, current_val, correction, count(*) votes
from verifications
where field = 'pos' and vote = 'wrong'
group by word, current_val, correction
order by votes desc;

-- Consensus per word: how many said correct vs wrong
select word, field,
       count(*) filter (where vote='correct') as ok,
       count(*) filter (where vote='wrong')   as bad
from verifications
group by word, field
having count(*) >= 3
order by bad desc;
```

You can later feed these corrections back into `Handoff/words.db` — the column
layout mirrors the old `import_verifications.py` (pos / final / livedead / lead /
cats), so a similar importer can pull from Supabase instead of a JSON file.

---

## Tuning

- **Votes needed per word:** change `< 3` in `get_words` *and* `>= 3` in
  `field_stats` (schema.sql), plus `VOTES_NEEDED` in `index.html`.
- **Buffer size / refill point:** `BUFFER_SIZE` / `REFILL_AT` in `index.html`.
- **Scoring:** `addScore()` in `index.html` and the `leaderboard` function.
