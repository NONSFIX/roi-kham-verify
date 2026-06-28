-- ============================================================================
--  Roi-Kham QUIZ + ADMIN — extra Supabase objects (run AFTER schema.sql)
--  Paste this whole file once in the Supabase SQL Editor (Dashboard → SQL).
--
--  The game is an anonymous quiz. Supabase is used to (a) hand the quiz random
--  words and (b) hold a queue of word add/edit/delete requests submitted from
--  admin.html. Nothing is written to `words` from the browser — the queue is
--  applied by add_words.py (service-role key) on your machine.
-- ============================================================================

-- ── quiz_words: random single words with their properties (the game deck) ───
create or replace function quiz_words(p_count int default 25)
returns table (
  word text, syllables int, pos text, final_class text,
  live_dead text, leading_class text, categories text
)
language sql security definer set search_path = public stable
as $$
  select w.word, w.syllables, w.pos, w.final_class,
         w.live_dead, w.leading_class, w.categories
  from words w
  where w.word not like '% %'        -- one word per card
  order by random()
  limit greatest(1, least(p_count, 100));
$$;
grant execute on function quiz_words(int) to anon, authenticated;

-- ── pending_words: the admin queue (add / edit / delete requests) ───────────
create table if not exists pending_words (
  id           bigint generated always as identity primary key,
  action       text not null default 'add',     -- 'add' | 'edit' | 'delete'
  word         text not null,
  overrides    jsonb,                            -- manual property overrides (optional)
  note         text,
  status       text not null default 'pending',  -- 'pending' | 'done' | 'error'
  result       text,
  created_at   timestamptz default now(),
  processed_at timestamptz
);
create index if not exists idx_pending_status on pending_words (status);

alter table pending_words enable row level security;

-- admin.html (anon key) may READ, ADD to, and CURATE the queue (set a category
-- / remove a row before it is processed). `words` itself is still only written
-- by add_words.py with the service-role key.
drop policy if exists "read pending"   on pending_words;
drop policy if exists "insert pending" on pending_words;
drop policy if exists "update pending" on pending_words;
drop policy if exists "delete pending" on pending_words;
create policy "read pending"   on pending_words for select to anon, authenticated using (true);
create policy "insert pending" on pending_words for insert to anon, authenticated with check (true);
create policy "update pending" on pending_words for update to anon, authenticated using (true) with check (true);
create policy "delete pending" on pending_words for delete to anon, authenticated using (true);
grant select, insert, update, delete on pending_words to anon, authenticated;

-- ── syllables: per-syllable data for the ทายมาตรา (final-class) quiz ─────────
-- Built by:  python add_words.py --build-split
create table if not exists syllables (
  syllable    text primary key,
  final_class text
);
alter table syllables enable row level security;
drop policy if exists "read syllables" on syllables;
create policy "read syllables" on syllables for select to anon, authenticated using (true);
grant select on syllables to anon, authenticated;

-- quiz_syllables: random syllables shaped like quiz_words so the game card +
-- genQFinal work unchanged (word = the syllable).
create or replace function quiz_syllables(p_count int default 25)
returns table (
  word text, syllables int, pos text, final_class text,
  live_dead text, leading_class text, categories text
)
language sql security definer set search_path = public stable
as $$
  select s.syllable as word, 1 as syllables, '' as pos, s.final_class,
         '' as live_dead, '' as leading_class, '' as categories
  from syllables s
  order by random()
  limit greatest(1, least(p_count, 100));
$$;
grant execute on function quiz_syllables(int) to anon, authenticated;

-- ============================================================================
--  Done. Next:
--   1. Open admin.html and add / edit / delete words (no password).
--   2. Run:  python add_words.py --process       (applies the queue into `words`)
--   3. Run:  python add_words.py --build-split    (fills `syllables` for ทายมาตรา)
-- ============================================================================
