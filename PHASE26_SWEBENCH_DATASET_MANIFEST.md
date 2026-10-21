# Phase 2.6 official dataset manifest

Dataset: **SWE-bench/SWE-bench_Verified**. Pinned revision: `78f471bf655a3137b2e8a75af1501690ec009ec3`.
Harness: SWE-bench 5.0.2 / `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`.
Task repository inspected at `3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`.

Subset: **SWE-bench Verified — Internal 20-Instance Subset**, `curated-20-v1`.
Immutable manifest hash: `bca369a9dc0d61df6398a72ea0042b6f89c7f23a66758c8fd444e84574accf89`.

* Metadata imported: **500**. Import prepared no task images.
* Selected: **20**, five each from four repositories.
* Images actually prepared: **16**.
* Gold reference evaluations resolved: **13**.
* Genuine unmodified-repository negative evaluations unresolved: **13**.
* Executable/graded-ready: **13**. Remaining **7 BLOCKED**.

All timestamps below are UTC. Relative evidence paths are under
`data/phase26-swebench-20261021T135404Z/`. The JSON manifest at
`output/final-dataset-manifest.json` includes actual image/report/patch/configuration
hashes and official evaluation IDs. Raw evaluation artifacts include protected
answers and must stay operator-only.

## Selection method and scope

Five lexicographically first instance IDs for each of sympy/sympy,
pytest-dev/pytest, sphinx-doc/sphinx and psf/requests, with the upstream documented
`sympy__sympy-20590` example anchored before SymPy sorting. This reproducible local
policy targets four independent repositories and differing issue content. It is
not a statistical sample of the full 500 and no difficulty labels were invented.
The dataset's original `difficulty` field remains private source metadata; it was
not used to advertise a representative difficulty distribution.

Stages were actually gated: one SymPy gold/unmodified/invalid/empty check, then
five instances across all four repositories, then expansion to the selected 20.
Execution concurrency was one per validation command. Existing prepared images
and completed evidence were reused. Later code changes prompted genuine rechecks
of three instances affected by environment-warning classification.

## Actual preparation and grading

| Instance ID | Repository | Preparation | Gold result | Negative result | Readiness | Latest observation UTC | Evidence |
|---|---|---|---|---|---|---|---|
| sympy__sympy-20590 | sympy/sympy | prepared | resolved | unresolved | PASS | 2026-10-21T14:11:21.143045+00:00 | runtime/datasets/evaluations/sec-ec3565f0b99602b2fc4f221d-e7c6e0a8953d/safe-result.json |
| sympy__sympy-11618 | sympy/sympy | prepared | resolved | unresolved | PASS | 2026-10-21T14:18:35.423741+00:00 | runtime/datasets/evaluations/sec-44b94880bcdd49067c293bc4-2c6bc90dd71c/safe-result.json |
| sympy__sympy-12096 | sympy/sympy | prepared | resolved | unresolved | PASS | 2026-10-21T14:35:01.569814+00:00 | runtime/datasets/evaluations/sec-0a42f89028e5053c365213d8-72d0cb4754cf/safe-result.json |
| sympy__sympy-12419 | sympy/sympy | prepared | resolved | unresolved | PASS | 2026-10-21T14:35:57.631508+00:00 | runtime/datasets/evaluations/sec-8b224bb26edf8ac5388cb6a4-439762801fbb/safe-result.json |
| sympy__sympy-12481 | sympy/sympy | prepared | resolved | unresolved | PASS | 2026-10-21T14:36:52.659403+00:00 | runtime/datasets/evaluations/sec-d8a2eaafefae371a9abc768c-eb8e3628986b/safe-result.json |
| pytest-dev__pytest-10051 | pytest-dev/pytest | prepared | resolved | unresolved | PASS | 2026-10-21T14:15:25.953500+00:00 | runtime/datasets/evaluations/sec-cd0ca22012b109f2510d39a4-ca0dbbac6900/safe-result.json |
| pytest-dev__pytest-10081 | pytest-dev/pytest | BLOCKED | NOT TESTED | NOT TESTED | BLOCKED | 2026-10-21T14:24:26.139292+00:00 | runtime/datasets/preparation/pytest-dev__pytest-10081-684e8c34dde54fd09c89d9349a87eaac.log |
| pytest-dev__pytest-10356 | pytest-dev/pytest | BLOCKED | NOT TESTED | NOT TESTED | BLOCKED | 2026-10-21T14:24:51.458414+00:00 | runtime/datasets/preparation/pytest-dev__pytest-10356-552bd10edaa8402fa231b13c9768db69.log |
| pytest-dev__pytest-5262 | pytest-dev/pytest | prepared | resolved | unresolved | PASS | 2026-10-21T15:28:01.220170+00:00 | runtime/datasets/evaluations/sec-68935d5bc049d052f3e6fe18-4d7aadea8e9c/safe-result.json |
| pytest-dev__pytest-5631 | pytest-dev/pytest | prepared | resolved | unresolved | PASS | 2026-10-21T15:28:53.625232+00:00 | runtime/datasets/evaluations/sec-790e28bcab67e82ba9a150fe-08e0054ddac6/safe-result.json |
| sphinx-doc__sphinx-10323 | sphinx-doc/sphinx | prepared | resolved | unresolved | PASS | 2026-10-21T14:17:14.193558+00:00 | runtime/datasets/evaluations/sec-f939623393ce9f2cefa64d40-c3998f71fc1c/safe-result.json |
| sphinx-doc__sphinx-10435 | sphinx-doc/sphinx | prepared | environment_failure | NOT TESTED | BLOCKED | 2026-10-21T14:29:56.288465+00:00 | runtime/datasets/evaluations/sec-18d25872e3dca1826b4709c4-92cb1b636876/safe-result.json |
| sphinx-doc__sphinx-10449 | sphinx-doc/sphinx | prepared | resolved | unresolved | PASS | 2026-10-21T14:30:53.990344+00:00 | runtime/datasets/evaluations/sec-96bfe62c4bd94afeb443a4d1-520636414173/safe-result.json |
| sphinx-doc__sphinx-10466 | sphinx-doc/sphinx | prepared | resolved | unresolved | PASS | 2026-10-21T14:31:53.769683+00:00 | runtime/datasets/evaluations/sec-613c23d6a944513f110bc21b-b4ce56c93c5d/safe-result.json |
| sphinx-doc__sphinx-10614 | sphinx-doc/sphinx | prepared | resolved | unresolved | PASS | 2026-10-21T15:30:02.517175+00:00 | runtime/datasets/evaluations/sec-547ea040eae8a93cf48010d1-d8355bc8cebb/safe-result.json |
| psf__requests-1142 | psf/requests | prepared | resolved | unresolved | PASS | 2026-10-21T14:13:41.807627+00:00 | runtime/datasets/evaluations/sec-dcecead62cb88e63dcb6ddea-70bf523d7450/safe-result.json |
| psf__requests-1724 | psf/requests | prepared | environment_failure | NOT TESTED | BLOCKED | 2026-10-21T14:22:44.891759+00:00 | runtime/datasets/evaluations/sec-b5a7f3c9f3b8cdafef14fc37-fa81c613abf6/safe-result.json |
| psf__requests-1766 | psf/requests | prepared | environment_failure | NOT TESTED | BLOCKED | 2026-10-21T14:54:03.513882+00:00 | runtime/datasets/evaluations/sec-355a07b542255b7ad4899827-a9b666961e71/safe-result.json |
| psf__requests-1921 | psf/requests | BLOCKED | NOT TESTED | NOT TESTED | BLOCKED | 2026-10-21T14:54:09.828831+00:00 | runtime/datasets/preparation/psf__requests-1921-a9312db84b4d402291c62d2d854843ea.log |
| psf__requests-2317 | psf/requests | BLOCKED | NOT TESTED | NOT TESTED | BLOCKED | 2026-10-21T15:10:02.200838+00:00 | runtime/datasets/preparation/psf__requests-2317-8a9a9918c5894bf1be1d7cda6df663c4.log |

## Limitations

Gold/unmodified results above are actual official-harness results, not metadata
readiness or handcrafted task substitutions. Reference patch application alone
never establishes PASS. Empty predictions are upstream-skipped, not executed
negative tests. Invalid patch rejection, a genuine test timeout, environment
failures, missing-preparation errors and cache-identity contracts are separately
covered in the acceptance report.

Five initial image preparations encountered registry EOF/DNS failures. One later
retry prepared an image but its gold evaluation encountered a network fault; four
remain blocked at preparation, including one safely interrupted stalled retry.
Three prepared gold environments require network unavailable under
the enforced candidate network-none policy. They stay BLOCKED; no internet was
enabled for candidate tests to force success. Other tasks remain executable.
The template supports a dedicated Linux x86_64 deployment; native x86_64 execution
and source-based official task-image rebuilds were not exercised in this ARM64
audit. A successful registry pull or metadata import is never called validation.

All gold checks are dataset integrity observations, excluded from model scores.
Stub-driven agent attempts are infrastructure evidence, not real model capability
measurements. No full SWE-bench score or public ranking is produced.
