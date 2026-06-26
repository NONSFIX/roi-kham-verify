-- ============================================================================
--  Roi-Kham Word Verification — Supabase schema
--  Run this whole file once in the Supabase SQL Editor (Dashboard → SQL).
-- ============================================================================

-- ── Tables ──────────────────────────────────────────────────────────────────

-- Master word list (filled by import_words.py)
create table if not exists words (
  word          text primary key,
  syllables     int,
  pos           text,
  final_class   text,
  live_dead     text,
  leading_class text,
  categories    text default ''
);

-- Every vote a player makes
create table if not exists verifications (
  id          bigint generated always as identity primary key,
  word        text not null,
  field       text not null,   -- 'pos' | 'final_class' | 'live_dead' | 'leading_class' | 'categories'
  vote        text not null,   -- 'correct' | 'wrong'
  current_val text,            -- value shown to the player
  correction  text,            -- player's fix (null when vote = 'correct')
  nickname    text,
  device_id   text,
  created_at  timestamptz default now()
);

-- Indexes that make the distribution & stats functions fast
create index if not exists idx_verif_field_word on verifications (field, word);
create index if not exists idx_verif_nickname   on verifications (nickname);

-- ── Config ──────────────────────────────────────────────────────────────────
-- How many votes a (word, field) needs before it's considered "done" and is
-- no longer handed out. Change here and re-run the get_words / field_stats defs.
--   VOTES_NEEDED = 3   (referenced inline below)

-- ── Row Level Security ──────────────────────────────────────────────────────
alter table words         enable row level security;
alter table verifications enable row level security;

-- Anyone (anon) may READ the word list...
drop policy if exists "read words" on words;
create policy "read words" on words
  for select to anon, authenticated using (true);

-- ...and INSERT a vote. They cannot read raw votes directly (kept private);
-- all reads of votes go through the security-definer functions below.
drop policy if exists "insert votes" on verifications;
create policy "insert votes" on verifications
  for insert to anon, authenticated with check (true);

grant select on words to anon, authenticated;
grant insert on verifications to anon, authenticated;

-- ── get_words: hand out the LEAST-voted words first ─────────────────────────
-- Returns words for the given field that still need votes (< 3), least-voted
-- first, with random tie-breaking so two players rarely get the same order.
create or replace function get_words(p_field text, p_count int default 25)
returns table (
  word text, syllables int, pos text, final_class text,
  live_dead text, leading_class text, categories text
)
language sql
security definer
set search_path = public
stable
as $$
  with vc as (
    select v.word, count(*) as votes
    from verifications v
    where v.field = p_field
    group by v.word
  )
  select w.word, w.syllables, w.pos, w.final_class,
         w.live_dead, w.leading_class, w.categories
  from words w
  left join vc on vc.word = w.word
  where coalesce(vc.votes, 0) < 3          -- VOTES_NEEDED
  order by coalesce(vc.votes, 0) asc, random()
  limit greatest(1, least(p_count, 100));
$$;

-- ── field_stats: progress bar for a given mode ──────────────────────────────
create or replace function field_stats(p_field text)
returns table (done bigint, total bigint)
language sql
security definer
set search_path = public
stable
as $$
  select
    (select count(*) from (
        select word from verifications
        where field = p_field
        group by word having count(*) >= 3      -- VOTES_NEEDED
     ) t)::bigint as done,
    (select count(*) from words)::bigint as total;
$$;

-- ── leaderboard: top players by score ───────────────────────────────────────
-- Score = 10 per confirmation, 20 per correction (matches the client).
create or replace function leaderboard(p_limit int default 10)
returns table (nickname text, score bigint, total bigint)
language sql
security definer
set search_path = public
stable
as $$
  select nickname,
         sum(case when vote = 'wrong' then 20 else 10 end)::bigint as score,
         count(*)::bigint as total
  from verifications
  where coalesce(nickname, '') <> ''
  group by nickname
  order by score desc
  limit greatest(1, least(p_limit, 100));
$$;

grant execute on function get_words(text, int)   to anon, authenticated;
grant execute on function field_stats(text)       to anon, authenticated;
grant execute on function leaderboard(int)        to anon, authenticated;

-- ============================================================================
--  Done. Next: run import_words.py to load the words, then paste your project
--  URL + anon key into webapp/index.html.
-- ============================================================================
