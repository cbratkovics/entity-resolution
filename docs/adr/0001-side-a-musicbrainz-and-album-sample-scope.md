# ADR-0001 — Side A is MusicBrainz release groups; sample scope is Album release groups (2026-09-23)

**Context.** `docs/BRIEF.md` section `2.1` leaves side A open between MusicBrainz release
groups (candidate #1) and Wikidata items carrying P1954 (candidate #3), to be decided from the
Phase 1 profile (`docs/PROFILE.md`, `artifacts/profile/`). The profile measured, against the
same Discogs masters dump, 347,237 alive truth pairs for MusicBrainz and 163,352 for Wikidata.
<!-- cite: artifacts/profile/musicbrainz.json#truth.alive; artifacts/profile/wikidata.json#truth.alive -->
The dead-id rate is 0.7% for MusicBrainz and 0.9% for Wikidata. <!-- cite: artifacts/profile/musicbrainz.json#truth.dead_rate; artifacts/profile/wikidata.json#truth.dead_rate -->
Wikidata's population was selected by having P1954, so every one of its 164,711 items is
linked by construction; it has no unlinked A records, and on that side coverage and accuracy
would be the same number. <!-- cite: artifacts/profile/wikidata.json#records.total -->
Only 91.8% of its items carry an English label. <!-- cite: artifacts/profile/wikidata.json#records.completeness.title -->

**Decision.**

1. *Side A is MusicBrainz release groups.* `PROJECT.side_a = "musicbrainz"`. Wikidata stays in
   `docs/DATA_SOURCES.md` as profiled and rejected, and its profile artifact is kept.
2. *Sample scope.* Side A is release groups of primary type Album only, 2,324,821 records; side B
   is all 2,589,349 masters. <!-- cite: artifacts/profile/musicbrainz.json#records.albums; artifacts/profile/discogs.json#records.total -->
   The sample holds every alive Album truth pair, 242,542 of them, plus hash-selected unlinked
   records to an unlinked share of `0.50` on each side. <!-- cite: artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.Album -->
   Links whose release group is a Single (71,985), an EP (31,437) or another type are a scope
   exclusion: the truth audit counts them as `truth_out_of_scope`, separately from
   `truth_unsampled` (hash-excluded) and `truth_dead`. <!-- cite: artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.Single; artifacts/profile/musicbrainz.json#truth.a_records_with_link_by_primary_type.EP -->
   Masters linked only from out-of-scope release groups stay eligible as B distractors and carry
   the flag `b_linked_out_of_scope` in the sample, so Phase 4 can report false positives that
   involve them.
3. *Evaluation scoping* (amends sections `2.7` and `2.9`). Labels exist only for A records with
   a truth link. Pairs whose A record is unlabelled are scored but excluded from fitting and
   calibration; precision, recall against labelled pairs, F1 and calibration are computed over
   labelled A records only. Accepts on unlabelled A records are reported separately as
   `unverified_accepts` (count and share): coverage counts them, the accuracy metrics do not.
   This is the coverage-versus-accuracy exhibit. Unlinked B records remain in blocking as
   distractors for labelled A records.
4. *Deferred checks.* The 41,408 alive pairs that fall outside every listed name-convention
   pattern are not re-examined now; they are revisited only if union pair completeness in
   Phase 3 is below `0.95`. <!-- cite: artifacts/profile/musicbrainz.json#truth.pattern_counts.other -->
   Phase 3 must count alive pairs where both sides are flagged various-artists but the
   normalised credits differ; if that explains most of the 21,631 `artist_credit_join` pairs,
   various-artists credits are canonicalised to one token in `normalize.py` with a
   `FEATURE_VERSION` bump and the profile is regenerated. <!-- cite: artifacts/profile/musicbrainz.json#truth.pattern_counts.artist_credit_join -->

Alternatives: Wikidata as side A, rejected for the reasons in the context; all release-group
types as the scope, deferred to `docs/ROADMAP.md` as a second, harder run.

**Consequences.** The Phase 2 adapters are Discogs and MusicBrainz; the ten-table list of
ADR-0002 applies. `artifacts/truth_audit.json` gains `truth_out_of_scope`; the sample gains
`b_linked_out_of_scope`; the evaluation artifact gains `unverified_accepts`. Limitations
(`docs/FINDINGS.md`) must carry: the scope exclusion of non-Album release groups, the
hash-excluded and dead truth links, unlinked is not non-match, recall is against labelled pairs
only, and ADR-0002's first-release year equivalence being asserted, not verified.
`docs/ROADMAP.md` gains the all-types run and Wikidata as a third source.
