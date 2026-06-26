-- ============================================================================
--  PATCH: stop the swipe game from serving multi-word entries
--  Problem: get_words handed out phrases like "ก ข ไม่กระดิกหู" and royal
--  titles (2+ words on one card), confusing players about which word to verify.
--  Fix: only serve single-word entries (word has no space).
--
--  Run this whole file once in the Supabase SQL Editor (Dashboard → SQL).
--  It just replaces two functions — no data is deleted; the 611 multi-word
--  entries simply stop being handed out (and stop counting toward the total).
-- ============================================================================

-- get_words: least-voted words first, now skipping multi-word phrases.
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
    and w.word not like '% %'              -- skip multi-word phrases (one word per card)
  order by coalesce(vc.votes, 0) asc, random()
  limit greatest(1, least(p_count, 100));
$$;

-- field_stats: keep the progress bar honest — total = servable single words only.
create or replace function field_stats(p_field text)
returns table (done bigint, total bigint)
language sql
security definer
set search_path = public
stable
as $$
  select
    (select count(distinct word) from verifications
       where field = p_field)::bigint as done,
    (select count(*) from words where word not like '% %')::bigint as total;
$$;

-- Sanity check (optional): how many multi-word entries are now excluded.
-- select count(*) as excluded_multiword from words where word like '% %';
