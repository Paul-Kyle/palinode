---
id: project-my-app-status
category: project-status
entities: [project/my-app, person/alice, person/bob]
last_updated: 2026-03-29
consolidation_passes: 2
---

# My App — Status (Pass 2: after MERGE + ARCHIVE)

> This is what the status file looks like after the weekly full pass ran MERGE and ARCHIVE. 11 lines, down from 23 in pass 0. Related facts have been consolidated into single lines; superseded entries have been moved to `archive/2026/my-app-status.md` (nothing was deleted). This is the file you'd actually want to read when opening the project fresh.

## Current Work

- [2026-03-09] Stack: React Native (Expo); Bob has 2y Expo experience. <!-- fact: f-0309-1m merged_from: [f-0308-1, f-0309-1] -->
- [2026-03-15] **Decision: REST over GraphQL** for checkout API. See `decisions/api-design.md`. Rationale: Stripe webhooks are REST-native; tRPC ruled out by Python service plans; GraphQL flexibility wasn't needed. <!-- fact: f-0315-1m merged_from: [f-0310-1, f-0311-1, f-0312-1, f-0313-1, f-0315-1] -->
- [2026-03-18] Stripe integration complete. Webhook signing uses raw body middleware. <!-- fact: f-0318-1m merged_from: [f-0316-1, f-0317-1, f-0318-1, f-0319-1, f-0324-1, f-0324-2] -->
- [2026-03-20] QA edge cases found: expired cards, 3DS, address mismatch. <!-- fact: f-0320-1 op: KEEP -->
- [2026-03-21] Expired card handling: fixed. <!-- fact: f-0321-1 op: KEEP -->
- [2026-03-22] 3DS flow: added, needs more testing. <!-- fact: f-0322-1 op: KEEP -->
- [2026-03-23] Address mismatch: deferred to post-launch. <!-- fact: f-0323-1 op: KEEP -->
- [2026-03-25] QA pass 1 complete. <!-- fact: f-0325-1 op: UPDATE from: "2 blockers remaining" reason: blockers were fixed 03-26 and 03-27 -->
- [2026-03-27] Launch blockers resolved: cart persistence (iOS), Apple Pay sheet dismissal (iOS 17). <!-- fact: f-0327-1m merged_from: [f-0326-1, f-0327-1] -->
- [2026-03-28] Apple Pay confirmed as launch requirement (per Alice 2026-03-18). <!-- fact: f-0328-1m merged_from: [f-0327-2, f-0328-1] -->
- [2026-03-28] **Launch target: 2026-04-15. On track.** <!-- fact: f-0328-2 op: KEEP -->

## Open Questions

- Error handling UX for declined cards — show inline or modal?

## Consolidation Log

### 2026-03-29 (nightly pass)
<!-- 13 ops: see pass-1-after-update-supersede.md for details -->

### 2026-03-30 (weekly full pass)
- [MERGE] f-0308-1 + f-0309-1 → f-0309-1m: combined stack decision lines
- [MERGE] f-0310-1 + f-0311-1 + f-0312-1 + f-0313-1 + f-0315-1 → f-0315-1m: combined API decision journey
- [MERGE] f-0316-1 + f-0317-1 + f-0318-1 + f-0319-1 + f-0324-1 + f-0324-2 → f-0318-1m: combined Stripe integration narrative
- [MERGE] f-0326-1 + f-0327-1 → f-0327-1m: combined launch blocker resolutions
- [MERGE] f-0327-2 + f-0328-1 → f-0328-1m: combined Apple Pay clarification
- [ARCHIVE] f-0308-1 → `archive/2026/my-app-status.md`: superseded, preserved in archive
- [ARCHIVE] f-0310-1 → `archive/2026/my-app-status.md`: superseded, preserved in archive
- [ARCHIVE] f-0311-1 → `archive/2026/my-app-status.md`: superseded, preserved in archive
- [ARCHIVE] f-0317-1 → `archive/2026/my-app-status.md`: superseded, preserved in archive
- [ARCHIVE] f-0324-1 → `archive/2026/my-app-status.md`: superseded, preserved in archive
- [UPDATE] f-0325-1: removed blocker count (blockers were resolved in f-0327-1m)
- [UPDATE] f-0328-2: emphasized launch date as the headline status
