# Handoff

_Read this first after `/clear` to resume the immediate next micro-task. Update this file at the end of every major task — before context is cleared — so the next session can pick up cold._

## Just completed

Systematically re-verified all 11 specific bugs in `docs/audits/DECOMMISSION_TASK_LIST.md` against current code — **every one was already fixed**, none required new code changes this session. Last one checked was the alembic fresh-DB migration claim: spun up a throwaway local Postgres cluster (`initdb`/`pg_ctl` on port 5433, socket in `/tmp/pg_fresh_test_sock` — long scratchpad paths broke the Postgres 103-byte Unix-socket-path limit, that's why `/tmp` directly), ran `alembic upgrade head` with `DATABASE_URL` overridden via env var (pydantic-settings gives env vars precedence over `.env`, so the real dev DB config was never touched) against a blank database — all 20 migrations applied cleanly. Cluster was stopped and deleted afterward; nothing persisted outside the session. `current-state.md` now documents this as a fully re-verified, fully stale audit list — see it for the full per-item breakdown.

Also earlier this session: moved 13 docs from repo root into `docs/{guides,testing,audits}/`, fixed cross-references in README.md/CLAUDE.md.

No production code was changed this session — verification only.

## Immediate next task

The decommission list's specific-bug backlog is exhausted (all fixed). What's left is genuinely different in kind: **5 duplicate/orphaned-implementation "which version wins" decisions**, listed in `current-state.md` under "Remaining open backlog." These aren't bugs to fix — they're product/architecture calls (which of 2-3 real implementations becomes canonical, and whether to decommission the others). None have been re-verified this session; before proposing a consolidation, first re-check each one is still accurately described (given how stale the rest of this doc turned out to be).

Suggested entry point if picking this up: **game situations** — the audit claims `enhanced_game_situation_service.py` is "the most rigorous, best-documented code in the entire audit" but has zero frontend callers, while a less-rigorous version is what's actually wired to `AdvancedAnalysisPage.tsx`. High value if true (better logic sitting unused), but confirm the "zero callers" and "more rigorous" claims first — grep for `enhanced_game_situation_service` imports and diff the two implementations' actual statistical methods before deciding anything.

Otherwise: ask the user whether they'd rather tackle a consolidation decision, or consider the backlog closed out and look for new work (e.g., resume something from `docs/audits/UX_PRODUCT_REVIEW.md`'s long-term deferred section, or `DEFERRED_FEATURES_CHECKLIST.md`'s push-alerts MVP).

## Critical technical context

- **This session's core lesson**: `docs/audits/DECOMMISSION_TASK_LIST.md` (and by extension any point-in-time audit doc in this repo) decays fast. Always re-verify against current code/tests before treating a listed item as an open task — don't just relay the doc's claims.
- **Local throwaway-Postgres recipe** (useful again for any future fresh-DB/migration testing): `initdb -D <dir> -U testuser -A trust`, then `pg_ctl -D <dir> -o "-p <port> -k <short-socket-dir>" -l <logfile> start` — the socket directory must be short (Postgres caps the full socket path at 103 bytes), so don't use this session's long scratchpad path; `/tmp/<name>` works. Override `DATABASE_URL` as an env var when invoking `alembic`/the app — pydantic-settings' `SettingsConfigDict(env_file=".env")` gives real env vars precedence over `.env`, so this never touches the actual dev DB config.
- **Grading engines**: `roster_grading.py::grade_roster` is real, deterministic, ESPN-only, already wired into `roster-analysis`.
- **Comparison rule** (confirmed correctly applied everywhere): `UserLeague.platform` is a plain `enum.Enum` — always `.value.upper()` against a string literal.

## State of the working tree at handoff time

Docs move is staged (`git mv`, history preserved) but **not committed** — confirm with the user before committing. `README.md`/`CLAUDE.md` have unstaged cross-reference-fix edits. `current-state.md`/`handoff.md`/`memory.md` are untracked (never committed — ask the user if these should be committed too, or stay local-only). Pre-existing unrelated diff still present and untouched:
```
D .claude/skills/optimize-prompt.md
?? .claude/skills/optimize-prompt/
```
