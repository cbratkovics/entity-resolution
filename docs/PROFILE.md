# Source profile (Phase 1)

<!-- generated:profile start -->
_Rendered by `scripts/profile_sources.py render` from `artifacts/profile/*.json`; do not edit_
_the generated block by hand. Every figure below is the artifact value; the key is the column._

## Side by side

| measure | Discogs masters (B) | MusicBrainz release groups (A #1) | Wikidata P1954 items (A #3) | key |
|---|---|---|---|---|
| records | 2,589,349 | 4,526,113 | 164,711 | `records.total` |
| title completeness | 100.0% | 100.0% | 91.8% | `records.completeness.title` |
| artist credit completeness | 100.0% | 100.0% | 96.5% | `records.completeness.artist_credit` |
| year completeness | 93.3% | 95.6% | 98.3% | `records.completeness.year` |
| year out of [1900, next year] | 18 | 1,159 | 2 | `records.year.out_of_range` |
| various-artists share | 6.4% | 6.4% | 2.4% | `records.various_artists_share` |
| self-titled share | 3.1% | 2.5% | 3.3% | `records.self_titled_share` |
| bracketed edition qualifier share | 0.1% | 0.1% | 0.0% | `records.qualifier_share` |
| records sharing a (title_norm, artist_norm) key | 4.5% | 3.2% | 8.3% | `records.duplicate_key.record_rate` |
| largest duplicate key | 414 | 140 | 1,198 | `records.duplicate_key.largest_key_size` |
| numeric artist disambiguator share | 11.5% | n/a | n/a | `records.numeric_disambiguator_share` |
| acquisition bytes | 0.58 GiB | 7.02 GiB | n/a | `acquisition.bytes` |
| download time | 0.3 min | 4.8 min | n/a | `acquisition.download_seconds` |
| extract time | n/a | 21.7 min | n/a | `acquisition.extract_seconds` |
| extracted bytes | n/a | 4.47 GiB | n/a | `acquisition.extracted_bytes` |
| endpoint requests | n/a | n/a | 664 | `acquisition.requests` |
| endpoint request time | n/a | n/a | 19.7 min | `acquisition.request_seconds` |
| endpoint retries / failures | n/a | n/a | 4 | `acquisition.timeouts` |
| profile time | 3.9 min | 11.6 min | 22.2 min | `acquisition.profile_seconds` |
| truth links to Discogs masters | n/a | 349,509 | 164,805 | `truth.links` |
| truth links alive in the current dump | n/a | 347,237 | 163,352 | `truth.alive` |
| truth dead-id rate | n/a | 0.7% | 0.9% | `truth.dead_rate` |
| A records with more than one master | n/a | 0.3% | 0.1% | `truth.one_to_many_a_rate` |
| masters linked from more than one A record | n/a | 0.6% | 0.9% | `truth.one_to_many_b_rate` |
| alive links with artist and year on A | n/a | 344,954 | 155,222 | `truth.alive_with_artist_and_year` |

## Year distribution by decade

| decade | Discogs | MusicBrainz | Wikidata |
|---|---|---|---|
| 1900s | 1,256 | 1,873 | n/a |
| 1910s | 3,819 | 744 | 2 |
| 1920s | 9,492 | 3,516 | 10 |
| 1930s | 10,044 | 5,547 | 42 |
| 1940s | 14,427 | 7,652 | 187 |
| 1950s | 84,037 | 19,132 | 2,505 |
| 1960s | 178,623 | 53,232 | 8,217 |
| 1970s | 237,184 | 92,329 | 16,227 |
| 1980s | 283,515 | 163,827 | 23,147 |
| 1990s | 429,591 | 444,672 | 34,230 |
| 2000s | 430,439 | 774,485 | 42,344 |
| 2010s | 483,264 | 1,341,031 | 28,548 |
| 2020s | 250,271 | 1,416,799 | 6,505 |

## MusicBrainz release groups by primary type

| primary type | release groups |
|---|---|
| Album | 2,324,821 |
| Single | 1,424,165 |
| EP | 582,515 |
| none | 102,495 |
| Other | 64,426 |
| Broadcast | 27,691 |

Discogs link types on release groups (`truth.link_type_counts`): discogs 349,509. Discogs URLs that are not master URLs (release or artist pages): 7 (`truth.discogs_non_master_urls`).

## Wikidata items by class (top 10, `records.by_class_top`)

| P31 class | items |
|---|---|
| Q105543609 | 2,100 |
| Q10590726 | 430 |
| Q107154516 | 27 |
| Q11424 | 172 |
| Q134556 | 23,096 |
| Q169930 | 5,015 |
| Q482994 | 133,223 |
| Q60713210 | 27 |
| Q7366 | 132 |
| none | 27 |

Server-side COUNT of P1954 items: 164,910 (`acquisition.server_count`); items paged locally: 164,711 (`records.total`); items with an English label: 91.8% (`records.with_english_label`); P1954 values that are not numeric: 92 (`truth.non_numeric_ids`).

## Name-convention patterns over alive truth pairs: MusicBrainz (`truth.pattern_counts`)

| pattern | pairs | share of alive | description |
|---|---|---|---|
| `identical` | 239,326 | 68.9% | normalised title, artist and year all equal |
| `other` | 41,408 | 11.9% | title or artist differ in a way none of the listed patterns explains |
| `artist_credit_join` | 21,631 | 6.2% | one artist credit's tokens are a strict subset of the other's (joined credit vs single artist) |
| `year_only` | 18,532 | 5.3% | normalised title and artist equal; the year differs or is missing on one side |
| `title_token_subset` | 18,472 | 5.3% | one title's tokens are a strict subset of the other's (subtitle or extra words) |
| `self_titled_vs_named` | 2,537 | 0.7% | one side's title equals its artist (self-titled) and the other's does not |
| `various_artists_credit` | 2,242 | 0.6% | one side credits Various Artists and the other names artists |
| `numeric_disambiguator` | 2,103 | 0.6% | the Discogs artist credit carries a numeric disambiguator such as '(2)' |
| `title_token_order` | 662 | 0.2% | same title tokens in a different order |
| `article_position` | 255 | 0.1% | the artist article is trailing on one side ('X, The') and leading on the other |
| `edition_qualifier` | 68 | 0.0% | one side carries a bracketed edition qualifier (remaster, deluxe, ...) that the other omits |
| `case_punct_diacritics` | 1 | 0.0% | raw strings differ only in case, punctuation or diacritics (equal after basic normalisation) |

### 15 examples (`examples[i]`): hashes of the normalised strings, never the strings

| # | pattern | A title sha256 (12) | B title sha256 (12) | A artist sha256 (12) | B artist sha256 (12) | year A | year B | description |
|---|---|---|---|---|---|---|---|---|
| 0 | `other` | `c8768df7e237` | `06fc0d0acf54` | `603d3d668b55` | `603d3d668b55` | 1979 | 1979 | title or artist differ in a way none of the listed patterns explains |
| 1 | `artist_credit_join` | `b2cf25a72877` | `b2cf25a72877` | `52a7427a9de5` | `1d35a94841cb` | 2003 | 2003 | one artist credit's tokens are a strict subset of the other's (joined credit vs single artist) |
| 2 | `year_only` | `a9e300bc3c03` | `a9e300bc3c03` | `0ce0b996d47e` | `0ce0b996d47e` | 2017 | 2014 | normalised title and artist equal; the year differs or is missing on one side |
| 3 | `title_token_subset` | `10a53daf4b12` | `b651dce0a1ef` | `bbeb81a9068d` | `bbeb81a9068d` | 1995 | 1994 | one title's tokens are a strict subset of the other's (subtitle or extra words) |
| 4 | `self_titled_vs_named` | `b5ffce9768d6` | `b5ffce9768d6` | `d67bcd79c1e2` | `b5ffce9768d6` | 2011 | 2011 | one side's title equals its artist (self-titled) and the other's does not |
| 5 | `various_artists_credit` | `a3c96f4a18ff` | `b8798b6f989d` | `52a7427a9de5` | `033fd73fab8e` | 2002 | 2002 | one side credits Various Artists and the other names artists |
| 6 | `numeric_disambiguator` | `4f8d4d59152e` | `4f8d4d59152e` | `8148ce5043b5` | `8148ce5043b5` | 1999 | 2000 | the Discogs artist credit carries a numeric disambiguator such as '(2)' |
| 7 | `title_token_order` | `46e4d1eddb4b` | `cdd6dc65cff8` | `f30dfced7fa0` | `f30dfced7fa0` | 1942 | 1942 | same title tokens in a different order |
| 8 | `article_position` | `e122609c668f` | `e122609c668f` | `eecaae36639b` | `eecaae36639b` | 1990 | 1992 | the artist article is trailing on one side ('X, The') and leading on the other |
| 9 | `edition_qualifier` | `97b8b81a21cf` | `51945df720a5` | `5685c57de6c8` | `5685c57de6c8` | 2010 | 2010 | one side carries a bracketed edition qualifier (remaster, deluxe, ...) that the other omits |
| 10 | `case_punct_diacritics` | `740002563b6e` | `8753ba4f638d` | `6c28fdc944ea` | `20574c961908` | 2016 | 2016 | raw strings differ only in case, punctuation or diacritics (equal after basic normalisation) |
| 11 | `other` | `8c4d75368654` | `8c4d75368654` | `9dfe5b603e86` | `844ee75d7808` | 2007 | 2006 | title or artist differ in a way none of the listed patterns explains |
| 12 | `artist_credit_join` | `549804174a22` | `549804174a22` | `52a7427a9de5` | `1d35a94841cb` | 1993 | 1993 | one artist credit's tokens are a strict subset of the other's (joined credit vs single artist) |
| 13 | `year_only` | `40a4d2acfa50` | `40a4d2acfa50` | `9514ff29f90f` | `9514ff29f90f` | 1971 | 1972 | normalised title and artist equal; the year differs or is missing on one side |
| 14 | `title_token_subset` | `4e2edd4fe291` | `1bc71d643dd3` | `7b1c9ca524d6` | `7b1c9ca524d6` | 2014 | 2014 | one title's tokens are a strict subset of the other's (subtitle or extra words) |

## Name-convention patterns over alive truth pairs: Wikidata (`truth.pattern_counts`)

| pattern | pairs | share of alive | description |
|---|---|---|---|
| `identical` | 105,175 | 64.4% | normalised title, artist and year all equal |
| `other` | 20,164 | 12.3% | title or artist differ in a way none of the listed patterns explains |
| `title_token_subset` | 15,050 | 9.2% | one title's tokens are a strict subset of the other's (subtitle or extra words) |
| `artist_credit_join` | 13,432 | 8.2% | one artist credit's tokens are a strict subset of the other's (joined credit vs single artist) |
| `year_only` | 6,281 | 3.8% | normalised title and artist equal; the year differs or is missing on one side |
| `self_titled_vs_named` | 1,686 | 1.0% | one side's title equals its artist (self-titled) and the other's does not |
| `various_artists_credit` | 681 | 0.4% | one side credits Various Artists and the other names artists |
| `numeric_disambiguator` | 588 | 0.4% | the Discogs artist credit carries a numeric disambiguator such as '(2)' |
| `title_token_order` | 204 | 0.1% | same title tokens in a different order |
| `article_position` | 62 | 0.0% | the artist article is trailing on one side ('X, The') and leading on the other |
| `edition_qualifier` | 25 | 0.0% | one side carries a bracketed edition qualifier (remaster, deluxe, ...) that the other omits |
| `case_punct_diacritics` | 4 | 0.0% | raw strings differ only in case, punctuation or diacritics (equal after basic normalisation) |

### 15 examples (`examples[i]`): hashes of the normalised strings, never the strings

| # | pattern | A title sha256 (12) | B title sha256 (12) | A artist sha256 (12) | B artist sha256 (12) | year A | year B | description |
|---|---|---|---|---|---|---|---|---|
| 0 | `other` | `339f0f4756b5` | `f737be38d861` | `e3b0c44298fc` | `8ff2483f2fba` | 1987 | 1987 | title or artist differ in a way none of the listed patterns explains |
| 1 | `title_token_subset` | `e3b0c44298fc` | `1c8be30e4657` | `93afcea41057` | `93afcea41057` | 1977 | 1977 | one title's tokens are a strict subset of the other's (subtitle or extra words) |
| 2 | `artist_credit_join` | `d0a53aae2ee8` | `d0a53aae2ee8` | `e3b0c44298fc` | `984e224e1b0d` | 2002 | 2002 | one artist credit's tokens are a strict subset of the other's (joined credit vs single artist) |
| 3 | `year_only` | `5c5dcb491de6` | `5c5dcb491de6` | `08343e62d894` | `08343e62d894` | 2005 | 2006 | normalised title and artist equal; the year differs or is missing on one side |
| 4 | `self_titled_vs_named` | `e3b0c44298fc` | `b6c61263ba60` | `e3b0c44298fc` | `b6c61263ba60` | 2007 | 2007 | one side's title equals its artist (self-titled) and the other's does not |
| 5 | `various_artists_credit` | `f63494cfb7a7` | `f63494cfb7a7` | `0fbac8c5342e` | `1d35a94841cb` | 2012 | 2012 | one side credits Various Artists and the other names artists |
| 6 | `numeric_disambiguator` | `60eed3086ab8` | `60eed3086ab8` | `5743abddddfa` | `5743abddddfa` | missing | 1991 | the Discogs artist credit carries a numeric disambiguator such as '(2)' |
| 7 | `title_token_order` | `fadba86cdfcb` | `d6c18b9e494a` | `64ad577a175e` | `64ad577a175e` | 1980 | 1980 | same title tokens in a different order |
| 8 | `article_position` | `62fe72bbdefd` | `62fe72bbdefd` | `bd829ff2661b` | `bd829ff2661b` | missing | 1964 | the artist article is trailing on one side ('X, The') and leading on the other |
| 9 | `edition_qualifier` | `0d46d552788e` | `b5e0eee6e28e` | `0bd9c428f627` | `0bd9c428f627` | 2007 | 2007 | one side carries a bracketed edition qualifier (remaster, deluxe, ...) that the other omits |
| 10 | `case_punct_diacritics` | `e649128bd8f4` | `d4f22194c921` | `e3b0c44298fc` | `ae497696da1d` | 2010 | 2010 | raw strings differ only in case, punctuation or diacritics (equal after basic normalisation) |
| 11 | `other` | `10808630f4aa` | `10808630f4aa` | `b4c8fd3d1b08` | `d719a12ec001` | 2004 | 2004 | title or artist differ in a way none of the listed patterns explains |
| 12 | `title_token_subset` | `f274d0ab4942` | `77e457ab4b52` | `198679765887` | `198679765887` | 1987 | 1987 | one title's tokens are a strict subset of the other's (subtitle or extra words) |
| 13 | `artist_credit_join` | `44ffb5c2c440` | `44ffb5c2c440` | `52a7427a9de5` | `1d35a94841cb` | 2006 | 2006 | one artist credit's tokens are a strict subset of the other's (joined credit vs single artist) |
| 14 | `year_only` | `6eafd5e8e182` | `6eafd5e8e182` | `68ce588f6b6b` | `68ce588f6b6b` | missing | 1982 | normalised title and artist equal; the year differs or is missing on one side |

<!-- generated:profile end -->
## Recommendation

Written after the profile; every number is the artifact value it cites.

### Candidate #1: MusicBrainz release groups

- **Truth pairs in scope.** 349,509 release-group-to-master links, of which 347,237 point at a
  master present in the current Discogs dump. <!-- cite: artifacts/profile/musicbrainz.json#truth.links; artifacts/profile/musicbrainz.json#truth.alive -->
  Of the linked release groups, 242,542 are of primary type Album, 71,985 Single and 31,437 EP.
  <!-- cite: artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.Album; artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.Single; artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.EP -->
- **Acquisition cost.** One archive of 7,542,238,956 bytes (`7.02 GiB`), downloaded in 288.1 seconds. <!-- cite: artifacts/profile/musicbrainz.json#acquisition.bytes; artifacts/profile/musicbrainz.json#acquisition.download_seconds -->
  Stream-extracting the ten tables took 1,299.1 seconds over 2 passes and left 4,795,695,166 bytes (`4.47 GiB`) on disk.
  <!-- cite: artifacts/profile/musicbrainz.json#acquisition.extract_seconds; artifacts/profile/musicbrainz.json#acquisition.extract_passes; artifacts/profile/musicbrainz.json#acquisition.extracted_bytes -->
  Profiling the 4,526,113 release groups took 695.3 seconds. <!-- cite: artifacts/profile/musicbrainz.json#records.total; artifacts/profile/musicbrainz.json#acquisition.profile_seconds -->
  The second pass exists because `release_group_meta` is not in the core archive (ADR 0002).
- **Truth quality.** Dead-id rate 0.7%; 0.3% of linked release groups point at more than one
  master and 0.6% of linked masters are pointed at by more than one release group.
  <!-- cite: artifacts/profile/musicbrainz.json#truth.dead_rate; artifacts/profile/musicbrainz.json#truth.one_to_many_a_rate; artifacts/profile/musicbrainz.json#truth.one_to_many_b_rate -->
  Every one of the 349,509 links is typed `discogs` by MusicBrainz and only 7 Discogs URLs on
  release groups are not master URLs. <!-- cite: artifacts/profile/musicbrainz.json#truth.links; artifacts/profile/musicbrainz.json#truth.discogs_non_master_urls -->
  Among alive pairs, 239,326 are identical after normalisation and 41,408 fall outside every
  listed pattern. <!-- cite: artifacts/profile/musicbrainz.json#truth.pattern_counts.identical; artifacts/profile/musicbrainz.json#truth.pattern_counts.other -->
- **Fields.** Year present on 95.6% of release groups; 6.4% are various-artists credits.
  <!-- cite: artifacts/profile/musicbrainz.json#records.completeness.year; artifacts/profile/musicbrainz.json#records.various_artists_share -->

### Candidate #3: Wikidata items with P1954

- **Truth pairs in scope.** 164,805 P1954 statements over 164,711 items, of which 163,352 point
  at a master in the current dump. <!-- cite: artifacts/profile/wikidata.json#truth.links; artifacts/profile/wikidata.json#records.total; artifacts/profile/wikidata.json#truth.alive -->
  The server-side count was 164,910, so the paged local count is complete to within the churn
  of the query window. <!-- cite: artifacts/profile/wikidata.json#acquisition.server_count -->
- **Acquisition cost.** No dump: 664 SPARQL requests in 1,179.4 seconds with 4 failed
  attempts retried, all responses hashed and cached. <!-- cite: artifacts/profile/wikidata.json#acquisition.requests; artifacts/profile/wikidata.json#acquisition.request_seconds; artifacts/profile/wikidata.json#acquisition.timeouts -->
  A grouped query, or one with an optional label on the item list, crashes the endpoint, so
  every attribute is a separate flat query; the profile took 1,331.2 seconds end to end.
  <!-- cite: artifacts/profile/wikidata.json#acquisition.profile_seconds -->
- **Truth quality.** Dead-id rate 0.9%; 0.1% of items carry more than one master id and 0.9%
  of linked masters are claimed by more than one item; 92 P1954 values are not numeric.
  <!-- cite: artifacts/profile/wikidata.json#truth.dead_rate; artifacts/profile/wikidata.json#truth.one_to_many_a_rate; artifacts/profile/wikidata.json#truth.one_to_many_b_rate; artifacts/profile/wikidata.json#truth.non_numeric_ids -->
- **Fields.** Only 91.8% of items have an English label and 96.5% a performer; 155,222 alive
  links have both a performer and a year. <!-- cite: artifacts/profile/wikidata.json#records.completeness.title; artifacts/profile/wikidata.json#records.completeness.artist_credit; artifacts/profile/wikidata.json#truth.alive_with_artist_and_year -->
  8.3% of items share a normalised (title, artist) key with another item and the largest such
  key holds 1,198 items, because items without an English label normalise to an empty title.
  <!-- cite: artifacts/profile/wikidata.json#records.duplicate_key.record_rate; artifacts/profile/wikidata.json#records.duplicate_key.largest_key_size -->
  The top class holds 133,223 items and the next 23,096. <!-- cite: artifacts/profile/wikidata.json#records.by_class_top.Q482994; artifacts/profile/wikidata.json#records.by_class_top.Q134556 -->
- **Structural limitation.** The items were selected by having P1954, so every side-A record in
  a Wikidata sample is linked by construction. There is no unlinked A population, which means the
  coverage-versus-accuracy comparison the brief exists to show cannot be made on side A; it could
  only be made on the Discogs side.

### Proposed side A and sample scope

**Side A: MusicBrainz release groups (candidate #1).** It has more than twice the alive truth
pairs, complete titles and credits, a slightly lower dead-id rate, and above all an unlinked
population of the same record type as the linked one, so "unlinked" is a real outcome rather
than an artefact of selection. <!-- cite: artifacts/profile/musicbrainz.json#truth.alive; artifacts/profile/wikidata.json#truth.alive -->
The costs are a 7,542,238,956-byte (`7.02 GiB`) download and a two-pass extraction on every full build, both measured
above. <!-- cite: artifacts/profile/musicbrainz.json#acquisition.bytes -->

**Scope: release groups of primary type Album, whole dump, both sides.**

- A population: the 2,324,821 Album release groups; B population: all 2,589,349 masters (Discogs
  masters are album-level works with no type field). <!-- cite: artifacts/profile/musicbrainz.json#records.albums; artifacts/profile/discogs.json#records.total -->
- Truth pairs in scope: the 242,542 alive links whose release group is an Album.
  <!-- cite: artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.Album -->
  Restricting to Album drops the Single and EP links; they are kept as a
  Limitations entry, not silently excluded, and are counted as `truth_unsampled`.
- Sample: every alive Album truth pair, plus hash-selected unlinked Album release groups and
  unlinked masters with an unlinked share of one half on each side, so the sampled A and B sides
  each hold about twice the linked count. <!-- param --> That gives roughly 485,000 A records
  and 485,000 B records, with the `test` fold holding a fifth of the B records and of the truth
  pairs by construction. <!-- param -->
- Expected candidate pairs: not estimable before the blocking keys exist (Phase 3); the per-A cap
  of 200 bounds the union at 200 times the A count, and the duplicate-key rates above (4.5% of
  masters and 3.2% of release groups share a normalised key) are the first sign of how big the
  exact-title blocks will be. <!-- cite: artifacts/profile/discogs.json#records.duplicate_key.record_rate; artifacts/profile/musicbrainz.json#records.duplicate_key.record_rate -->
- Alternative if a larger sample is wanted: all release-group types with the same unlinked share
  (twice the 347,237 alive links as A records). <!-- cite: artifacts/profile/musicbrainz.json#truth.alive -->

Nothing below this line is decided until ADR-0001 records the owner's choice of side A and
sample scope.
