# Data sources

Every source must carry an explicit, verbatim open licence recorded here with the URL it was
read from and the date (`docs/BRIEF.md` rule 1). Unstated licence = source dropped. Nothing
below has been downloaded yet: the licence texts, dump dates, sizes and hashes are recorded in
Phase 1 when the profiling script first reads them.

## Approved sources

| source | side | what is loaded | native id | licence |
|---|---|---|---|---|
| Discogs monthly data dump, `discogs_YYYYMMDD_masters.xml.gz` | B | `title`, artist credit as printed, `year`, `genres`, `main_release` | `master_id` | CC0 (to be recorded verbatim in Phase 1) |
| MusicBrainz core dump `mbdump.tar.bz2` | A candidate | tables `release_group`, `release_group_meta`, `artist_credit`, `release_group_primary_type`, `l_release_group_url`, `url`, `link`, `link_type` only | `release_group.gid` | CC0 (to be recorded verbatim in Phase 1) |
| Wikidata SPARQL, items with `P1954` | A candidate | `label@en`, `P175` performer labels, `P577` year, `P31` | `QID` | CC0 (to be recorded verbatim in Phase 1) |

## Deliberately not loaded

- Discogs submitter or contributor fields, MusicBrainz editor identifiers, and any other
  user-level field in supplementary dumps.
- Any MusicBrainz table beyond the eight listed above.
- Release-level (as opposed to master or release-group level) records.

## What enters git

Nothing from a dump. Titles, artist credits and every other record attribute stay under `data/`,
which is git-ignored and checked by `tests/test_gitignore.py` and `tests/test_no_raw_rows.py`.
