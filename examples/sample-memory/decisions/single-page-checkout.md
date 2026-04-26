---
id: decision-single-page-checkout
category: decision
core: false
entities: [project/my-app, person/alice]
last_updated: 2026-03-20
summary: "Single-page checkout over multi-step wizard. A/B test showed 23% higher completion rate."
---
# Decision: Single-Page Checkout

## What Was Decided
Use a single-page checkout flow instead of a multi-step wizard.

## Why
- A/B test on staging showed 23% higher completion rate with single-page
- Fewer page loads = faster on mobile networks
- Easier to implement error recovery (no state to lose between steps)

## Trade-offs Accepted
- Longer initial page load (more components up front)
- Address validation and payment fields visible together (could feel cluttered on small screens)

## Date
2026-03-20 — decided after reviewing A/B test results with Alice.
