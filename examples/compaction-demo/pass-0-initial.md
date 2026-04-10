---
id: project-my-app-status
category: project-status
entities: [project/my-app, person/alice, person/bob]
last_updated: 2026-03-28
---

# My App — Status (Pass 0: raw, 3 weeks of accretion)

> This is what a project status file looks like after three weeks of session-end hook appends without any compaction. Each bullet was written by a different session. Contradictions, duplicates, and outdated entries accumulate. Compare to `pass-1-after-update-supersede.md` to see what the nightly pass cleans up.

## Current Work

- [2026-03-08] Kicked off checkout redesign. Stack TBD — evaluating React Native vs Flutter. <!-- fact: f-0308-1 -->
- [2026-03-09] Decided on React Native. Bob has Expo experience. <!-- fact: f-0309-1 -->
- [2026-03-10] Starting API layer design. Considering GraphQL for flexibility. <!-- fact: f-0310-1 -->
- [2026-03-11] GraphQL exploration ongoing. Apollo Server looks promising. <!-- fact: f-0311-1 -->
- [2026-03-12] Actually, leaning REST now. Stripe webhooks are REST-native. <!-- fact: f-0312-1 -->
- [2026-03-13] Tried tRPC in a spike — nice DX but Python service plans rule it out. <!-- fact: f-0313-1 -->
- [2026-03-15] Decision: REST over GraphQL. Documented in decisions/api-design.md. <!-- fact: f-0315-1 -->
- [2026-03-16] Started Stripe SDK integration. Alice's track. <!-- fact: f-0316-1 -->
- [2026-03-17] Stripe integration blocked on webhook signing. Waiting on Bob. <!-- fact: f-0317-1 -->
- [2026-03-18] Webhook signing resolved — using raw body middleware. <!-- fact: f-0318-1 -->
- [2026-03-19] First end-to-end checkout succeeded in dev. <!-- fact: f-0319-1 -->
- [2026-03-20] QA caught three edge cases: expired cards, 3DS, address mismatch. <!-- fact: f-0320-1 -->
- [2026-03-21] Expired card handling fixed. <!-- fact: f-0321-1 -->
- [2026-03-22] 3DS flow added. Need more testing. <!-- fact: f-0322-1 -->
- [2026-03-23] Address mismatch deferred to post-launch. <!-- fact: f-0323-1 -->
- [2026-03-24] Stripe integration complete. All tests passing. <!-- fact: f-0324-1 -->
- [2026-03-24] Actually, Stripe was already done on the 18th. Just re-verified today. <!-- fact: f-0324-2 -->
- [2026-03-25] QA pass 1 complete. 2 blockers remaining. <!-- fact: f-0325-1 -->
- [2026-03-26] Blocker 1 fixed: cart persistence across app restarts. <!-- fact: f-0326-1 -->
- [2026-03-27] Blocker 2 fixed: Apple Pay sheet dismissing early on iOS 17. <!-- fact: f-0327-1 -->
- [2026-03-27] Apple Pay was supposed to be post-launch. Why is it a blocker? <!-- fact: f-0327-2 -->
- [2026-03-28] Clarified: Apple Pay is a launch requirement per Alice's note on 03-18. <!-- fact: f-0328-1 -->
- [2026-03-28] Launch target still April 15. On track. <!-- fact: f-0328-2 -->

## Open Questions

- Do we need Apple Pay / Google Pay for launch or can it wait?
  <!-- answered 2026-03-28 but the question is still here -->
- Error handling UX for declined cards — show inline or modal?
  <!-- still open -->

## Consolidation Log

<!-- empty — no compaction has run yet -->
