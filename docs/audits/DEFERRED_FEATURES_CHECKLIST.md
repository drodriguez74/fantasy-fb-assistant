# Deferred Features — Task Checklist

Derived from the current state of the published "Fourth Down, Long Yardage" UX review artifact. Of 19 tracked items, 17 are `✓ Done` (see `UX_PRODUCT_REVIEW.md` / `UX_TASK_CHECKLIST.md` for the full history). This checklist covers the 2 remaining.

## Immediate — requires the founder directly, not agent-workable
- [ ] Rotate the ESPN session cookie (log out/in to ESPN)
- [ ] Decide whether to rewrite local git history to purge the old commit containing that cookie

## Near-Term — scoped and built this pass

- [x] ~~Keeper league support (MVP)~~ — **out of scope, per the founder directly**: "i don't care about keeper or dynasty leagues on traditional fantasy ppr ot standard." This product is scoped to traditional redraft PPR/Standard leagues; keeper/dynasty support is not being built. The agent building this was stopped immediately (it had only just started reading context, no code was written).

- [ ] **Push alerts (MVP, scoped to in-app notifications)**
  - Product decision made explicitly: true browser/device push (service workers, VAPID keys, a new secret to manage) is the largest possible first slice for an app with zero existing notification infrastructure. Building an in-app notification center instead delivers the real ask ("tell me when something changed") without inventing push infra from scratch. Device push stays explicit future scope, not silently dropped.
  - Backend: a lightweight notifications table + endpoint, populated by real events (waiver trending adds, injury status changes for a user's rostered/watched players).
  - Frontend: a bell icon + dropdown in the Navbar showing recent alerts, with a read/unread state.

## Verification requirement (per task)
Each item must be verified against the running app (real request/response or a real click-through with Playwright), not just "code compiles" — matching the standard applied to every other fix this session. `pytest` must stay green, `npm run build`/`lint` must stay clean.
