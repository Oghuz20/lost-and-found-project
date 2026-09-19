# Contribution Statement

**Team:** M503 Team 8
**Topic:** Topic 1 — Smart Lost & Found
**Repository:** [https://github.com/Oghuz20/lost-and-found-project](https://github.com/Oghuz20/lost-and-found-project)
**Final tag:** `v1.0-final`
**Submission date:** _[YYYY-MM-DD]_

---

## How to fill this in

This is the single piece of evidence we use to assess **individual contribution** within the team. Rules:

1. Every member writes their own three subsections (Owned, Co-owned, Reviewed).
2. **Be specific.** "Worked on the backend" is not acceptable; "implemented `src/services/ai_service.py` and `src/concurrency/pipeline.py`, owned PRs #4, #7, #11" is.
3. The committed-percentages must add to 100% and approximately match `git shortlog -sn` on the `main` branch.
4. All three members must sign at the bottom. Unsigned submissions are returned ungraded.

If one member contributed less than 10% without a documented reason (illness, emergency), the team loses 5 points automatically per the rubric.

---

## Member A — Sadiq Sadiqov (`@_[github-handle]_`)

**Owned (sole author of these files / PRs):**
- `src/config.py`
- `src/storage/repository.py` (PostgreSQL persistence + filesystem image storage)
- `src/storage/schema.sql`
- Alembic migration scripts (`migrations/`)
- `pgvector` extension setup and indexing configuration
- PRs: #_[list]_

**Co-owned (paired or substantially edited):**
- `src/api.py` (with Member B)
- `src/models.py` (storage-shaped base version, later merged by Member C — see Member C's co-owned list)
- `requirements.txt` / `requirements-dev.txt` (contributed storage-layer dependencies; consolidated by Member C)

**Reviewed (PRs reviewed and merged):**
- PRs: #_[list]_

**Approximate share of commits:** 34%

---

## Member B — Ülkər Kərimova (`@_[github-handle]_`)

**Owned (sole author of these files / PRs):**
- `src/api.py` — `POST /items/lost`, `POST /items/found`, `GET /items/{id}/matches`, with Pydantic request/response schema validation
- `src/services/vlm_pipeline.py` (Gemini VLM integration for structured image description extraction)
- `src/services/embedding.py` (`text-embedding-004` integration for dense vector embedding generation)
- `src/services/concurrency/batch_runner.py` (asynchronous, non-blocking batch execution workers)
- `src/services/concurrency/rate_limiter.py` (token-bucket rate limiter to eliminate HTTP 429 quota errors)
- PRs: #_[list]_

**Co-owned (paired or substantially edited):**
- `src/api.py` (with Member A)
- `src/cli.py` (`search-matches` implementation added on top of the initial skeleton, later merged by Member C — see Member C's co-owned list)

**Reviewed (PRs reviewed and merged):**
- PRs: #_[list]_

**Approximate share of commits:** 33%

> **Note to reconcile before submission:** an earlier draft of this section listed `src/telemetry/cost.py` under Member B's ownership. Member C's section below claims sole authorship of that file. Only one of you can be the sole author — confirm which, and if it was genuinely a joint effort, move it to both members' **Co-owned** lists instead of leaving it as a conflicting "Owned" claim in two places.

---

## Member C — Oğuz Həsənli (`@Oghuz20`)

**Owned (sole author of these files / PRs):**
- `src/services/ai_service.py`
- `src/services/cache.py`
- `src/logging_config.py`
- `src/validation.py`
- `src/telemetry/cost.py`
- `src/telemetry/tracing.py`
- `scripts/demo.py`
- `tests/test_ai_service.py`, `tests/test_validation.py`, `tests/test_end_to_end.py`, `tests/test_telemetry.py`, `tests/test_cli.py`
- PRs: #_[list once you have real PR numbers]_

**Co-owned (paired or substantially edited):**
- `src/models.py` (merged with Member A's storage-shaped version; added `is_active()`/`is_strong_match()`, removed Pydantic v1 syntax)
- `src/cli.py` (merged Member A's working `register-lost`/`register-found`/`list` with a `search-matches` implementation added on top of Member B's skeleton)
- `src/api.py` (status-filter case-sensitivity fix)
- `requirements.txt` / `requirements-dev.txt` (consolidated all three members' dependencies)
- `tests/conftest.py` (confirmed identical across all three submissions; no merge conflict in practice)

**Reviewed (PRs reviewed and merged):**
- `src/services/concurrency/batch_runner.py` (Member B) — caught and fixed a partial-batch-failure bug via mypy + a targeted test before it shipped
- `src/services/pipeline.py` (Member B) — caught a return-type mismatch masking the same batch-failure issue
- PRs: #_[list]_

**Approximate share of commits:** 33%

---

## AI tool disclosure (also in §9 of the report)

We used AI coding assistants as follows. Each item lists the module, the assistant, and what the team did with the output.

| Module / file | Assistant | What we did with it |
|---|---|---|
| `src/storage/` (schema, Alembic migrations, `pgvector` indexing) | Claude | Used to draft SQL schema constraints, migration scripts, and indexing parameters. All queries and schema definitions were validated against a local PostgreSQL instance. |
| `src/api.py`, `src/services/concurrency/`, `src/telemetry/cost.py` | Claude | Used to iteratively refine asynchronous batch processing logic and FastAPI schema validation models. Explicitly debugged and fixed: graceful handling of upstream HTTP 429 quota exhaustion, non-blocking execution during heavy Gemini calls, and a raw exception leak in a Pydantic model. All generated code was verified with local `pytest` runs. |
| `src/services/ai_service.py`, `src/telemetry/` | Claude | Drafted the retry/timeout/telemetry wrapper iteratively across many review rounds. Required and verified fixes for: a fake timeout that only measured elapsed time after the fact instead of enforcing one; a silent-exception leak that let non-`ProviderError` failures crash uncaught; an OpenTelemetry exporter misconfigured to retry against a nonexistent local collector; and a batch-runner bug (found during integration review) that discarded an entire batch of results when one item failed. Every fix was verified by rerunning the real test suite. |

We affirm that we **can defend every line of code** in this repository during the oral defense. "The AI wrote it" is not an answer we will use.

---

## Signatures

By signing below, we affirm that:
- The contributions described above are accurate.
- The commit percentages reflect actual work, not artificially split commits.
- Every line of code in the repository can be defended by at least one team member.
- AI assistant usage has been disclosed as described above.

| Member | Signature | Date |
|---|---|---|
| Sadiq Sadiqov | __________________________ | __________ |
| Ülkər Kərimova | __________________________ | __________ |
| Oğuz Həsənli | __________________________ | __________ |
