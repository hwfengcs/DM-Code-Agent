# DM-Code-Agent All Benchmark Report

- Total runs: `30`
- Overall pass rate: `73.3%`
- Hidden-test pass rate: `83.3%`
- Agent completion rate: `83.3%`

## Variant Summary

| Variant | Strict pass (95% CI) | Hidden pass | Agent done | Avg steps | Avg tools | Avg changed | Avg tokens | Cost | Cost/success | Requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full | 73.3% (22/30) [95% CI 55.6%-85.8%] | 83.3% | 83.3% | 11.67 | 10.77 | 1.27 | 48605 | $0.0000 | $0.0000 | 438 |

## Recovery

| Variant | Recovery success rate | Recovered | Runs with failures |
| --- | ---: | ---: | ---: |
| full | 72.7% | 16 | 22 |

## Capability by tag

| Tag | Pass | Runs |
| --- | ---: | ---: |
| algorithm | 71.4% (5/7) | 7 |
| bugfix | 100.0% (2/2) | 2 |
| business-logic | 100.0% (2/2) | 2 |
| ci | 0.0% (0/1) | 1 |
| cli | 0.0% (0/1) | 1 |
| code-understanding | 66.7% (2/3) | 3 |
| config | 50.0% (1/2) | 2 |
| cross-file | 66.7% (2/3) | 3 |
| data-cleaning | 100.0% (1/1) | 1 |
| data-structure | 100.0% (1/1) | 1 |
| database | 100.0% (1/1) | 1 |
| datetime | 100.0% (1/1) | 1 |
| dedupe | 100.0% (1/1) | 1 |
| docs | 0.0% (0/1) | 1 |
| edge-cases | 93.3% (14/15) | 15 |
| encoding | 100.0% (1/1) | 1 |
| error-handling | 100.0% (3/3) | 3 |
| filesystem | 100.0% (2/2) | 2 |
| git | 0.0% (0/1) | 1 |
| hidden-tests | 66.7% (2/3) | 3 |
| logging | 0.0% (0/1) | 1 |
| maintenance | 60.0% (9/15) | 15 |
| multi-file | 0.0% (0/2) | 2 |
| networking | 100.0% (1/1) | 1 |
| ordering | 0.0% (0/1) | 1 |
| packaging | 0.0% (0/1) | 1 |
| pagination | 100.0% (1/1) | 1 |
| parsing | 66.7% (2/3) | 3 |
| recursion | 100.0% (1/1) | 1 |
| regression | 40.0% (2/5) | 5 |
| reporting | 0.0% (0/1) | 1 |
| resilience | 100.0% (1/1) | 1 |
| security | 66.7% (2/3) | 3 |
| stateful | 80.0% (4/5) | 5 |
| string | 100.0% (3/3) | 3 |
| tests | 100.0% (2/2) | 2 |
| validation | 100.0% (1/1) | 1 |

## Failed Runs

- `full/ttl_cache_lru`: Response is not a valid JSON object.
- `full/semver_compare`: Max steps exceeded
- `full/config_precedence`:                                                                    [100%]
================================== FAILURES ===================================
_______________________ test_cli_overrides_env_and_file _______________________

    def test_cli_overrides_env_and_file():
        result = load_config(
            {"timeout": 10, "debug": False},
            env={"DM_TIMEOUT": "20", "DM_DEBUG": "false"},
            cli_args={"timeout": "5", "debug": "true"},
        )
>       assert result["timeout"] == 5
E       AssertionError: assert '5' == 5

tests\test_hidden_config_loader.py:10: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_hidden_config_loader.py::test_cli_overrides_env_and_file - ...
1 failed, 3 passed in 0.11s

- `full/patch_summary_name_status`: ew_name.py' != {'from': 'old_name.py', 'to': 'new_name.py'}
E         Use -v to get more diff

tests\test_hidden_patch_summary.py:11: AssertionError
_______________________ test_unknown_status_is_reported _______________________

    def test_unknown_status_is_reported():
        result = summarize_name_status(["??\tuntracked.txt"])
>       assert result["unknown"] == [{"status": "??", "path": "untracked.txt"}]
               ^^^^^^^^^^^^^^^^^
E       KeyError: 'unknown'

tests\test_hidden_patch_summary.py:19: KeyError
=========================== short test summary info ===========================
FAILED tests/test_hidden_patch_summary.py::test_renames_and_blank_lines_are_supported
FAILED tests/test_hidden_patch_summary.py::test_unknown_status_is_reported - ...
2 failed, 1 passed in 0.12s

- `full/cross_file_user_contract`: Max steps exceeded
- `full/cli_config_docs_contract`: Max steps exceeded
- `full/packaging_ci_contract`: Max steps exceeded
- `full/log_redaction`:                            [100%]
================================== FAILURES ===================================
_________________ test_partial_and_case_insensitive_key_match _________________

    def test_partial_and_case_insensitive_key_match():
        event = {'user_PASSWORD': 'x', 'Api_Key': 'y', 'AUTHORIZATION': 'z'}
        result = redact_event(event)
>       assert set(result.values()) == {'***'}
E       AssertionError: assert {'***', 'x'} == {'***'}
E         
E         Extra items in the left set:
E         'x'
E         Use -v to get more diff

tests\test_hidden_redact.py:16: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_hidden_redact.py::test_partial_and_case_insensitive_key_match
1 failed, 4 passed in 0.12s


## Run Details

| Variant | Task | Pass | Hidden rc | Changed files | Trace |
| --- | --- | ---: | ---: | --- | --- |
| full | slugify_cleanup | yes | 0 | `text_utils.py` | `bench_reports\ablation-scope-traces\all-full-slugify_cleanup-r0.jsonl` |
| full | order_total_edges | yes | 0 | `orders.py` | `bench_reports\ablation-scope-traces\all-full-order_total_edges-r0.jsonl` |
| full | ttl_cache_lru | no | 1 | `cache.py` | `bench_reports\ablation-scope-traces\all-full-ttl_cache_lru-r0.jsonl` |
| full | normalize_users | yes | 0 | `users.py` | `bench_reports\ablation-scope-traces\all-full-normalize_users-r0.jsonl` |
| full | stats_summary | yes | 0 | `stats.py` | `bench_reports\ablation-scope-traces\all-full-stats_summary-r0.jsonl` |
| full | inventory_reservations | yes | 0 | `inventory.py` | `bench_reports\ablation-scope-traces\all-full-inventory_reservations-r0.jsonl` |
| full | parse_duration | yes | 0 | `durations.py` | `bench_reports\ablation-scope-traces\all-full-parse_duration-r0.jsonl` |
| full | merge_intervals | yes | 0 | `intervals.py` | `bench_reports\ablation-scope-traces\all-full-merge_intervals-r0.jsonl` |
| full | retry_backoff_schedule | yes | 0 | `backoff.py` | `bench_reports\ablation-scope-traces\all-full-retry_backoff_schedule-r0.jsonl` |
| full | csv_row_parser | yes | 0 | `csv_row.py` | `bench_reports\ablation-scope-traces\all-full-csv_row_parser-r0.jsonl` |
| full | paginate_cursor | yes | 0 | `pagination.py` | `bench_reports\ablation-scope-traces\all-full-paginate_cursor-r0.jsonl` |
| full | semver_compare | no | 0 | `semver.py` | `bench_reports\ablation-scope-traces\all-full-semver_compare-r0.jsonl` |
| full | flatten_config | yes | 0 | `flatten.py` | `bench_reports\ablation-scope-traces\all-full-flatten_config-r0.jsonl` |
| full | rate_limiter_window | yes | 0 | `ratelimit.py` | `bench_reports\ablation-scope-traces\all-full-rate_limiter_window-r0.jsonl` |
| full | safe_int_parse | yes | 0 | `coercion.py` | `bench_reports\ablation-scope-traces\all-full-safe_int_parse-r0.jsonl` |
| full | config_precedence | no | 1 | `config_loader.py` | `bench_reports\ablation-scope-traces\all-full-config_precedence-r0.jsonl` |
| full | patch_summary_name_status | no | 1 | `patch_summary.py` | `bench_reports\ablation-scope-traces\all-full-patch_summary_name_status-r0.jsonl` |
| full | retry_regression_tests | yes | 0 | `retry.py`, `tests/test_retry.py` | `bench_reports\ablation-scope-traces\all-full-retry_regression_tests-r0.jsonl` |
| full | safe_workspace_join | yes | 0 | `workspace.py` | `bench_reports\ablation-scope-traces\all-full-safe_workspace_join-r0.jsonl` |
| full | cross_file_user_contract | no | 0 | `serializers.py`, `users.py` | `bench_reports\ablation-scope-traces\all-full-cross_file_user_contract-r0.jsonl` |
| full | cli_config_docs_contract | no | 0 | `cli_docs.py`, `docs/configuration.md`, `tests/test_public_cli_docs.py` | `bench_reports\ablation-scope-traces\all-full-cli_config_docs_contract-r0.jsonl` |
| full | packaging_ci_contract | no | 2 | `.github/workflows/ci.yml`, `packaging_contract.py`, `pyproject.toml`, `tests/test_public_packaging.py` | `bench_reports\ablation-scope-traces\all-full-packaging_ci_contract-r0.jsonl` |
| full | billing_period_boundary | yes | 0 | `billing.py` | `bench_reports\ablation-scope-traces\all-full-billing_period_boundary-r0.jsonl` |
| full | sql_where_builder | yes | 0 | `query.py` | `bench_reports\ablation-scope-traces\all-full-sql_where_builder-r0.jsonl` |
| full | idempotent_job_runner | yes | 0 | `jobs.py` | `bench_reports\ablation-scope-traces\all-full-idempotent_job_runner-r0.jsonl` |
| full | sort_stability_regression | yes | 0 | `ranking.py`, `tests/test_ranking.py` | `bench_reports\ablation-scope-traces\all-full-sort_stability_regression-r0.jsonl` |
| full | filename_sanitizer | yes | 0 | `filenames.py` | `bench_reports\ablation-scope-traces\all-full-filename_sanitizer-r0.jsonl` |
| full | error_propagation_contract | yes | 0 | `service.py` | `bench_reports\ablation-scope-traces\all-full-error_propagation_contract-r0.jsonl` |
| full | settings_env_precedence | yes | 0 | `settings.py` | `bench_reports\ablation-scope-traces\all-full-settings_env_precedence-r0.jsonl` |
| full | log_redaction | no | 1 | `redact.py` | `bench_reports\ablation-scope-traces\all-full-log_redaction-r0.jsonl` |
