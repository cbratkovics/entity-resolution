# ADR-0002 — MusicBrainz first-release year from core release tables (2026-09-22)

**Context.** `docs/BRIEF.md` section `2.1` lists `release_group_meta` among the tables to stream out of
the MusicBrainz core dump `mbdump.tar.bz2`, as the source of `first_release_date_year`. The
Phase 1 extraction scanned every member of the `20260919-002047` core archive and did not find
it: `release_group_meta` ships in `mbdump-derived.tar.bz2`, which the MusicBrainz download page
describes as "annotations, user ratings, user tags, and search indexes" and which the Data
License page places under Creative Commons Attribution-NonCommercial-ShareAlike `3.0`
(`docs/DATA_SOURCES.md`). Rule 1 admits CC0 data only, so the derived archive cannot be used.

**Decision.** Derive the first-release year from core tables: the minimum `date_year` over
`release_country` and `release_unknown_country` for every release whose `release.release_group`
is the group, ignoring year `0`. The three tables (`release`, `release_country`,
`release_unknown_country`) replace `release_group_meta` in the table list; they are streamed out
of the same core archive in a second pass, so nothing outside the list touches disk.
Alternatives: (a) download the derived archive and read only `first_release_date_year` from
`release_group_meta`, rejected because the archive is licensed as a whole and rule 1 requires an
explicit CC0 statement for what is loaded; (b) leave the year missing for MusicBrainz, rejected
because year agreement is a blocking key and a rule feature and the Phase 1 comparison would be
unfair to candidate #1.

**Consequences.** The core archive is streamed twice (both passes timed in
`artifacts/profile/musicbrainz.json#acquisition`). The derived year equals MusicBrainz's own
`first_release_date_year` by construction (that column is computed from the same release events)
but this is asserted, not verified, since the derived table is never downloaded. The Phase 2
MusicBrainz adapter must extract the same ten tables. `docs/BRIEF.md` section `2.1` is amended in the
amendments log.
