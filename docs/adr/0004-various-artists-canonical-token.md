# ADR-0004 — Various-artists credits normalise to one token (2026-09-23)

**Context.** ADR-0001 item 4 required a check before blocking: count alive in-sample pairs
where both sides are flagged various-artists but the normalised credits differ. On the Phase 2
sample at feature version `0.1.0`, 14,807 in-sample truth pairs have both sides flagged, 14,805
of them with differing `artist_norm`, and 10,294 of those were classified
`artist_credit_join` out of 17,923 such pairs in the sample. <!-- scratch -->
MusicBrainz writes the credit "Various Artists" and Discogs writes "Various"; after
normalisation those are two different strings and every blocking key or artist feature built on
them disagrees.

**Decision.** In `entity_resolution/features/normalize.py`, any credit in `VA_CREDITS` (various,
various artists, va, v/a) normalises to the single token `VA_CANONICAL` in both `artist_norm`
and `artist_norm_full`. `FEATURE_VERSION` becomes `0.2.0`. The Phase 2 stages were re-run so
the sample carries the new normalisation; sample membership is by native id, so every count
and threshold in the manifest and the truth audit must be unchanged, and the checkpoint
asserts it. The Phase 1 profile is a dated record at `0.1.0` and is not regenerated; ADR-0001
cites its numbers, and `docs/PROFILE.md` now states the feature version its patterns were
classified at.

**Consequences.** Various-artists pairs agree on the artist credit and are blocked on title
keys only (section `2.4`) as before; `artist_credit_join` in any later pattern count will be
smaller than in the profile for this reason alone. The numbers above came from an exploratory
query on the sample, not a committed artifact, and are marked as such.
