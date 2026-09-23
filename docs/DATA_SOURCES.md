# Data sources

Every source carries an explicit, verbatim open licence recorded here with the URL it was read
from and the date (`docs/BRIEF.md` rule 1). Unstated licence = source dropped. Dump filenames,
sizes, sha256 hashes and download timings are in `artifacts/profile/<source>.json` under
`acquisition`, and in `artifacts/manifest.json` once a run exists.

## Discogs monthly data dump (side B)

- Dump: `discogs_20260901_masters.xml.gz`, downloaded from
  `https://data.discogs.com/?download=data%2F2026%2Fdiscogs_20260901_masters.xml.gz`
  (`artifacts/profile/discogs.json#acquisition`).
- Licence, read from https://data.discogs.com/ on 2026-09-22, verbatim:
  > This data is made available under the CC0 No Rights Reserved license:
  > http://creativecommons.org/about/cc0
- Loaded: `title`, the artist credit as printed (each `artists/artist/name` followed by its
  `join` text), `year`, the count of `genres`, `main_release`; native id `master_id`.
- Not loaded: releases, artists and labels dumps; `data_quality`, `videos`, `styles`, `notes`,
  and any submitter or contributor field.

## MusicBrainz core dump (side-A candidate #1)

- Dump: `mbdump.tar.bz2` from the full export `20260919-002047`, downloaded from
  `https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20260919-002047/mbdump.tar.bz2`
  (`artifacts/profile/musicbrainz.json#acquisition`).
- Licence, read from https://musicbrainz.org/doc/About/Data_License on 2026-09-22, verbatim:
  > The MusicBrainz Database is split into two components for licensing purposes.
  > Core data: The core data of the database is licensed under the CC0, which is effectively
  > placing the data into the Public Domain. This means that anyone can download and use the
  > core data in any way they see fit. No restrictions, no worries!
  > Supplementary data: The remaining portions of the database are released under the Creative
  > Commons Attribution-NonCommercial-ShareAlike 3.0 license.
  The ten tables below are core data (`mbdump.tar.bz2` is the core export; supplementary data
  ships separately in `mbdump-derived.tar.bz2` and others, which are never downloaded).
- Loaded (stream-extracted from the archive; nothing else is unpacked): `release_group`,
  `artist_credit`, `release_group_primary_type`, `l_release_group_url`, `url`, `link`,
  `link_type`, and for the first-release year `release`, `release_country`,
  `release_unknown_country` (ADR 0002: `release_group_meta` is not in the core archive).
  Fields used: `release_group.name`, `artist_credit.name`, the minimum `date_year` of the
  group's release events, `release_group_primary_type.name`; native id `release_group.gid`.
- Truth links: `l_release_group_url` joined to `url` where the URL matches
  `^https?://(www\.)?discogs\.com/master/(\d+)`.
- Not loaded: every other table, in particular `editor`, `edit`, `release.name` and
  `release.barcode` beyond the join key, and anything under the derived export
  (`mbdump-derived.tar.bz2`: annotations, user ratings, user tags, search indexes, CC BY-NC-SA).

## Wikidata (side-A candidate #3, profiled and rejected by ADR-0001)

Profiled in Phase 1 and not used as side A: its population is selected by P1954, so it has no
unlinked A records (`artifacts/profile/wikidata.json` is kept as the record of that profile).
It is on the roadmap as a possible third source.

- Endpoint: `https://query.wikidata.org/sparql`, paged queries with a User-Agent and backoff,
  responses cached and hashed (`artifacts/profile/wikidata.json#acquisition`). Queried on
  2026-09-22. A dump is not used because only the items carrying `P1954` are needed.
- Licence, read from https://www.wikidata.org/wiki/Wikidata:Licensing on 2026-09-22, verbatim:
  > All structured data in the main, property and lexeme namespaces is made available under the
  > Creative Commons CC0 License (Public domain); text in other namespaces is made available
  > under the Creative Commons Attribution-ShareAlike 4.0 License.
  Labels and statements are structured data in the main namespace.
- Loaded: items with `P1954` (Discogs master ID), their English label (any-language fallback),
  `P175` performer labels, `P577` publication date (year), `P31` class; native id `QID`.
- Not loaded: descriptions, sitelinks, any other property.

## Deliberately not loaded from any source

User-level fields of every kind (Discogs submitters, MusicBrainz editors), release-level
records, cover art, external identifiers other than the Discogs master link.

## What enters git

Nothing from a dump or a response. Titles, artist credits and every other record attribute
stay under `data/`, which is git-ignored and checked by `tests/test_gitignore.py` and
`tests/test_no_raw_rows.py`; the profile artifacts carry counts, rates, hashes, timings and
enumerated pattern codes only, enforced by `artifacts/schemas/profile.schema.json`.
