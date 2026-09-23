# Roadmap

Out of scope for v1 (`docs/BRIEF.md` rule 12). Ideas land here, not in the pipeline.

- A third source, once the two-source comparison is published.
- Active learning over the review queue.
- A serving API or a frontend beyond the static Pages site.
- Release-level (not master-level) linkage.
- A second, harder run over all MusicBrainz release-group types (Single, EP, Other, Broadcast) rather than Album only (ADR-0001).
- Wikidata items with P1954 as a third source, profiled in Phase 1 and rejected as side A because every item is linked by construction (ADR-0001).
- Aggregate the first-release year per release group during extraction so the release tables never hit disk; the extracted tables are what pushes `data/` past a hosted runner's free disk (docs/REPRODUCIBILITY.md).
- Chunk the feature stage by A block so peak memory drops below the 9 GiB the current run records (docs/REPRODUCIBILITY.md).
- Half-refit stability check for `learned_v1` (refit on a random half of the fit fold, compare test precision); it measures variance, not leakage.
- Calibrate on decisions, not pairs: argmax over calibrated pair probabilities biases the chosen probability upward (docs/FINDINGS.md).
