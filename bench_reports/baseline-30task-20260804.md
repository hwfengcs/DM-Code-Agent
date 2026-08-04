# DM-Code-Agent All Benchmark Report

- Total runs: `30`
- Overall pass rate: `50.0%`
- Hidden-test pass rate: `90.0%`
- Agent completion rate: `80.0%`

## Variant Summary

| Variant | Strict pass (95% CI) | Hidden pass | Agent done | Avg steps | Avg tools | Avg changed | Avg tokens | Cost | Cost/success | Requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full | 50.0% (15/30) [95% CI 33.2%-66.8%] | 90.0% | 80.0% | 11.83 | 10.83 | 1.60 | 51466 | $0.0000 | $0.0000 | 443 |

## Recovery

| Variant | Recovery success rate | Recovered | Runs with failures |
| --- | ---: | ---: | ---: |
| full | 45.5% | 10 | 22 |

## Capability by tag

| Tag | Pass | Runs |
| --- | ---: | ---: |
| algorithm | 85.7% (6/7) | 7 |
| bugfix | 50.0% (1/2) | 2 |
| business-logic | 100.0% (2/2) | 2 |
| ci | 0.0% (0/1) | 1 |
| cli | 0.0% (0/1) | 1 |
| code-understanding | 33.3% (1/3) | 3 |
| config | 50.0% (1/2) | 2 |
| cross-file | 33.3% (1/3) | 3 |
| data-cleaning | 0.0% (0/1) | 1 |
| data-structure | 100.0% (1/1) | 1 |
| database | 0.0% (0/1) | 1 |
| datetime | 0.0% (0/1) | 1 |
| dedupe | 0.0% (0/1) | 1 |
| docs | 0.0% (0/1) | 1 |
| edge-cases | 73.3% (11/15) | 15 |
| encoding | 0.0% (0/1) | 1 |
| error-handling | 33.3% (1/3) | 3 |
| filesystem | 0.0% (0/2) | 2 |
| git | 0.0% (0/1) | 1 |
| hidden-tests | 33.3% (1/3) | 3 |
| logging | 0.0% (0/1) | 1 |
| maintenance | 20.0% (3/15) | 15 |
| multi-file | 0.0% (0/2) | 2 |
| networking | 100.0% (1/1) | 1 |
| ordering | 100.0% (1/1) | 1 |
| packaging | 0.0% (0/1) | 1 |
| pagination | 100.0% (1/1) | 1 |
| parsing | 100.0% (3/3) | 3 |
| recursion | 100.0% (1/1) | 1 |
| regression | 40.0% (2/5) | 5 |
| reporting | 0.0% (0/1) | 1 |
| resilience | 100.0% (1/1) | 1 |
| security | 0.0% (0/3) | 3 |
| stateful | 60.0% (3/5) | 5 |
| string | 66.7% (2/3) | 3 |
| tests | 100.0% (2/2) | 2 |
| validation | 100.0% (1/1) | 1 |

## Failed Runs

- `full/slugify_cleanup`: Max steps exceeded
- `full/ttl_cache_lru`: _removed_before_evicting_live_entries ________

    def test_expired_entries_are_removed_before_evicting_live_entries():
        clock = Clock()
        cache = TTLCache(max_size=2, ttl_seconds=5, clock=clock)
        cache.set("old", 1)
        clock.now = 6
        cache.set("new", 2)
        cache.set("third", 3)
        assert cache.get("old") is None
>       assert cache.get("new") == 2
E       AssertionError: assert None == 2
E        +  where None = get('new')
E        +    where get = <cache.TTLCache object at 0x000002630C5BAAD0>.get

tests\test_hidden_cache.py:31: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_hidden_cache.py::test_expired_entries_are_removed_before_evicting_live_entries
1 failed, 3 passed in 0.11s

- `full/normalize_users`: Max steps exceeded
- `full/config_precedence`: changed files outside allowed set: tests/test_public_config_loader.py
- `full/patch_summary_name_status`: Max steps exceeded
- `full/safe_workspace_join`: changed files outside allowed set: tests/test_public_workspace.py
- `full/cross_file_user_contract`: changed files outside allowed set: tests/test_public_user_serializers.py
- `full/cli_config_docs_contract`: Max steps exceeded
- `full/packaging_ci_contract`: Max steps exceeded
- `full/billing_period_boundary`: changed files outside allowed set: tests/test_public_billing.py
- `full/sql_where_builder`: changed files outside allowed set: tests/test_public_query.py
- `full/idempotent_job_runner`: Max steps exceeded
- `full/filename_sanitizer`: changed files outside allowed set: tests/test_public_filenames.py
- `full/error_propagation_contract`: changed files outside allowed set: tests/test_public_service.py
- `full/log_redaction`: changed files outside allowed set: tests/test_public_redact.py

## Run Details

| Variant | Task | Pass | Hidden rc | Changed files | Trace |
| --- | --- | ---: | ---: | --- | --- |
| full | slugify_cleanup | no | 0 | `text_utils.py` | `bench_reports\baseline-30task-traces\all-full-slugify_cleanup-r0.jsonl` |
| full | order_total_edges | yes | 0 | `orders.py` | `bench_reports\baseline-30task-traces\all-full-order_total_edges-r0.jsonl` |
| full | ttl_cache_lru | no | 1 | `cache.py` | `bench_reports\baseline-30task-traces\all-full-ttl_cache_lru-r0.jsonl` |
| full | normalize_users | no | 0 | `users.py` | `bench_reports\baseline-30task-traces\all-full-normalize_users-r0.jsonl` |
| full | stats_summary | yes | 0 | `stats.py` | `bench_reports\baseline-30task-traces\all-full-stats_summary-r0.jsonl` |
| full | inventory_reservations | yes | 0 | `inventory.py` | `bench_reports\baseline-30task-traces\all-full-inventory_reservations-r0.jsonl` |
| full | parse_duration | yes | 0 | `durations.py` | `bench_reports\baseline-30task-traces\all-full-parse_duration-r0.jsonl` |
| full | merge_intervals | yes | 0 | `intervals.py` | `bench_reports\baseline-30task-traces\all-full-merge_intervals-r0.jsonl` |
| full | retry_backoff_schedule | yes | 0 | `backoff.py` | `bench_reports\baseline-30task-traces\all-full-retry_backoff_schedule-r0.jsonl` |
| full | csv_row_parser | yes | 0 | `csv_row.py` | `bench_reports\baseline-30task-traces\all-full-csv_row_parser-r0.jsonl` |
| full | paginate_cursor | yes | 0 | `pagination.py` | `bench_reports\baseline-30task-traces\all-full-paginate_cursor-r0.jsonl` |
| full | semver_compare | yes | 0 | `semver.py` | `bench_reports\baseline-30task-traces\all-full-semver_compare-r0.jsonl` |
| full | flatten_config | yes | 0 | `flatten.py` | `bench_reports\baseline-30task-traces\all-full-flatten_config-r0.jsonl` |
| full | rate_limiter_window | yes | 0 | `ratelimit.py` | `bench_reports\baseline-30task-traces\all-full-rate_limiter_window-r0.jsonl` |
| full | safe_int_parse | yes | 0 | `coercion.py` | `bench_reports\baseline-30task-traces\all-full-safe_int_parse-r0.jsonl` |
| full | config_precedence | no | 0 | `config_loader.py`, `tests/test_public_config_loader.py` | `bench_reports\baseline-30task-traces\all-full-config_precedence-r0.jsonl` |
| full | patch_summary_name_status | no | 1 | `patch_summary.py`, `tests/test_public_patch_summary.py` | `bench_reports\baseline-30task-traces\all-full-patch_summary_name_status-r0.jsonl` |
| full | retry_regression_tests | yes | 0 | `retry.py`, `tests/test_retry.py` | `bench_reports\baseline-30task-traces\all-full-retry_regression_tests-r0.jsonl` |
| full | safe_workspace_join | no | 0 | `tests/test_public_workspace.py`, `workspace.py` | `bench_reports\baseline-30task-traces\all-full-safe_workspace_join-r0.jsonl` |
| full | cross_file_user_contract | no | 0 | `serializers.py`, `tests/test_public_user_serializers.py`, `users.py` | `bench_reports\baseline-30task-traces\all-full-cross_file_user_contract-r0.jsonl` |
| full | cli_config_docs_contract | no | 0 | `cli_docs.py`, `docs/configuration.md`, `tests/test_public_cli_docs.py` | `bench_reports\baseline-30task-traces\all-full-cli_config_docs_contract-r0.jsonl` |
| full | packaging_ci_contract | no | 1 | `.github/workflows/ci.yml`, `packaging_contract.py`, `pyproject.toml`, `tests/test_public_packaging.py` | `bench_reports\baseline-30task-traces\all-full-packaging_ci_contract-r0.jsonl` |
| full | billing_period_boundary | no | 0 | `billing.py`, `tests/test_public_billing.py` | `bench_reports\baseline-30task-traces\all-full-billing_period_boundary-r0.jsonl` |
| full | sql_where_builder | no | 0 | `query.py`, `tests/test_public_query.py` | `bench_reports\baseline-30task-traces\all-full-sql_where_builder-r0.jsonl` |
| full | idempotent_job_runner | no | 0 | `jobs.py`, `tests/test_public_jobs.py` | `bench_reports\baseline-30task-traces\all-full-idempotent_job_runner-r0.jsonl` |
| full | sort_stability_regression | yes | 0 | `ranking.py`, `tests/test_ranking.py` | `bench_reports\baseline-30task-traces\all-full-sort_stability_regression-r0.jsonl` |
| full | filename_sanitizer | no | 0 | `filenames.py`, `tests/test_public_filenames.py` | `bench_reports\baseline-30task-traces\all-full-filename_sanitizer-r0.jsonl` |
| full | error_propagation_contract | no | 0 | `service.py`, `tests/test_public_service.py` | `bench_reports\baseline-30task-traces\all-full-error_propagation_contract-r0.jsonl` |
| full | settings_env_precedence | yes | 0 | `settings.py` | `bench_reports\baseline-30task-traces\all-full-settings_env_precedence-r0.jsonl` |
| full | log_redaction | no | 0 | `redact.py`, `tests/test_public_redact.py` | `bench_reports\baseline-30task-traces\all-full-log_redaction-r0.jsonl` |
