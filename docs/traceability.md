# Traceability: acceptance criteria → tests

Every acceptance criterion in [user-stories.md](user-stories.md) and the non-functional requirements, with the tests that prove it. Backend tests are in `backend/tests/` and front-end tests in `frontend/src/`. CI runs all of them on every push, and runs the backend suite twice: on SQLite and on PostgreSQL with RabbitMQ.

`file::name` is a pytest test; *front end:* names a Vitest test.

## US-1: Submit a complaint and see it as a case immediately

| # | Criterion | Proved by |
|---|---|---|
| 1 | `201` with reference, status `new`, my tenant | `test_cases_api::test_create_case_returns_201_with_new_status_and_reference`, `test_cases_api::test_create_case_requires_authentication` |
| 2 | Returns without waiting for the AI | `test_outbox::test_creating_a_case_queues_exactly_one_analysis_job`, `test_case_review_api::test_no_suggestions_are_shown_before_the_analysis` |
| 3 | Invalid input → `422` by field, nothing created | `test_cases_api::test_create_case_rejects_invalid_input`; *front end:* `reports invalid fields with the labels on the form` |
| 4 | `received_at` as given or server time, never changed afterwards | `test_cases_api::test_create_case_without_received_at_uses_server_time`, `test_cases_api::test_received_at_cannot_be_changed_after_intake` |
| 5 | Exactly one job with case, tenant and correlation id | `test_outbox::test_creating_a_case_queues_exactly_one_analysis_job`, `test_outbox::test_job_carries_the_request_correlation_id`, `test_analysis_job_handler::test_the_message_payload_is_ids_only` |
| 6 | Queue down → case still saved, job sent later | `test_outbox::test_broker_outage_keeps_the_case_and_the_job_for_later`, `test_outbox::test_relay_publishes_pending_jobs_once` |
| 7 | Same `external_message_id` twice → the existing case | `test_cases_api::test_duplicate_external_message_id_returns_existing_case`, `test_outbox::test_a_duplicate_submission_does_not_queue_a_second_job`, `test_tenant_isolation::test_same_external_message_id_in_two_tenants_creates_two_cases`; *front end:* `creates one case however many times Create is pressed` |

## US-2: See the AI's suggestions with evidence

| # | Criterion | Proved by |
|---|---|---|
| 1 | Category, summary, priority, indicators | `test_case_review_api::test_the_analysed_case_shows_suggestions_with_evidence_and_provenance`, `test_analysis_job_handler::test_a_valid_answer_puts_the_case_in_awaiting_review_with_suggestions`, `test_ai_output::test_invalid_answers_are_rejected_with_a_reason` (the 400-character limit and the fixed lists) |
| 2 | Each indicator has a type, an FG21/1 driver and a quote | `test_ai_output::test_indicators_with_word_for_word_evidence_are_kept_with_their_driver` |
| 3 | The quote must be word for word, or the indicator is dropped | `test_ai_output::test_invented_or_paraphrased_evidence_is_dropped`, `test_ai_output::test_a_quote_spanning_a_line_break_still_counts`, `test_logging::test_logs_carry_ids_but_never_the_complaint_or_personal_data` (the warning) |
| 4 | While analysing: status `analysing`, no suggestions, the rest usable | `test_analysis_job_handler::test_a_model_outage_leaves_the_case_analysing_and_the_retry_resumes_it`, `test_case_review_api::test_no_suggestions_are_shown_before_the_analysis`; *front end:* `while analysing: a notice, and nothing to decide yet` |
| 5 | Invalid output: one retry, then `needs_human_review` with the reason | `test_analysis_job_handler::test_one_invalid_answer_is_retried_with_the_reason`, `test_analysis_job_handler::test_two_invalid_answers_send_the_case_to_human_review_with_the_reason`, `test_case_review_api::test_a_failed_analysis_shows_why_and_no_suggestion`; *front end:* `needing a person: the reason is shown` |
| 6 | Any indicator → priority at least `high`, in code | `test_ai_output::test_vulnerability_lifts_the_priority_to_at_least_high`, `test_ai_output::test_urgent_stays_urgent_with_vulnerability`, `test_ai_output::test_dropped_evidence_does_not_lift_the_priority` |
| 7 | Provider and model shown | `test_case_review_api::test_the_analysed_case_shows_suggestions_with_evidence_and_provenance` |

## US-3: Accept or override suggestions, with an audit trail

| # | Criterion | Proved by |
|---|---|---|
| 1 | Accept → final = suggestion, audited `accepted_suggestion` | `test_case_review_api::test_accepting_the_suggested_category`; *front end:* `accepting a suggestion sends exactly that value` |
| 2 | Override → my value, audited `override`, suggestion kept | `test_case_review_api::test_overriding_the_category_keeps_the_original_suggestion` |
| 3 | Same rules for priority | `test_case_review_api::test_priority_follows_the_same_rules` |
| 4 | Confirm or reject an indicator; a rejected one stays visible | `test_case_review_api::test_an_indicator_decision_is_stored_with_who_and_when`, `test_case_review_api::test_pending_is_not_a_decision`; *front end:* `rejecting an indicator keeps it visible as rejected` |
| 5 | Add an indicator the AI missed, with its own quote | `test_case_review_api::test_a_handler_can_add_an_indicator_the_ai_missed`, `test_case_review_api::test_a_handlers_evidence_must_be_in_the_complaint_too` |
| 6 | The change and its audit event in one transaction | `test_case_review_api::test_a_change_and_its_audit_event_are_saved_together_or_not_at_all` (the audit write fails, and the case write fails) |
| 7 | Audit events cannot be edited or deleted | `test_case_review_api::test_the_audit_trail_is_newest_first_and_cannot_be_changed` |
| 8 | Full audit trail, newest first | `test_case_review_api::test_the_audit_trail_is_newest_first_and_cannot_be_changed`, `test_cases_api::test_creating_a_case_writes_an_audit_event`; *front end:* `names fields and values as people say them` |

## US-4: Always see the regulatory deadlines

| # | Criterion | Proved by |
|---|---|---|
| 1 | SRC and final response deadlines in UK time | `test_deadlines::test_day_of_receipt_is_the_uk_date_not_the_utc_date`, `test_deadlines::test_final_response_deadline_is_end_of_day_56_calendar_days_later`, `test_deadlines::test_final_response_deadline_uses_uk_time_across_a_clock_change`, `test_case_deadlines_api::test_new_case_has_both_deadlines_and_a_countdown` |
| 2 | No weekends, and the tenant region's bank holidays | `test_business_calendar::test_weekdays_are_business_days_and_weekends_are_not`, `test_business_calendar::test_bank_holidays_and_substitute_days_are_not_business_days`, `test_business_calendar::test_bank_holidays_depend_on_the_region` |
| 3 | Friday 2026-12-18 → Wednesday 2026-12-23 17:00 | `test_deadlines::test_src_deadline_received_on_friday` |
| 4 | Wednesday 2026-12-23 → Wednesday 2026-12-30 17:00 | `test_deadlines::test_src_deadline_skips_christmas_and_the_boxing_day_substitute` |
| 5 | Received on Saturday → counted from Monday | `test_deadlines::test_src_deadline_received_on_saturday_counts_from_monday` |
| 6 | Business days remaining; negative and overdue once passed | `test_deadlines::test_business_days_remaining_before_the_deadline`, `test_deadlines::test_due_today_is_zero_and_not_overdue_until_the_deadline_time`, `test_deadlines::test_missed_today_is_one_business_day_overdue`, `test_deadlines::test_overdue_counts_business_days_since_the_deadline`, `test_case_deadlines_api::test_countdown_is_recalculated_on_every_read` |
| 7 | Resolved → no countdown, in time or not | `test_deadlines::test_summary_resolution_by_the_src_deadline_is_in_time`, `test_deadlines::test_summary_resolution_after_the_src_deadline_is_late`, `test_deadlines::test_final_response_is_judged_against_the_eight_week_deadline` |
| 8 | A pure function, with "now" passed in | every test in `test_deadlines.py` passes its own `now`; `test_deadlines::test_naive_datetimes_are_refused` |
| 9 | Bank holidays from a local file that can be refreshed | `test_bank_holidays::test_the_bundled_file_loads_for_every_region`, `test_bank_holidays::test_the_bundled_file_matches_the_gov_uk_format`, `test_bank_holidays::test_a_feed_missing_a_region_is_rejected`, `test_business_calendar::test_a_date_outside_the_holiday_data_is_refused_not_guessed` |

## US-5: Team lead dashboard

| # | Criterion | Proved by |
|---|---|---|
| 1 | At risk, overdue, categories, confirmed vulnerability | `test_dashboard_api::test_deadline_counts`, `test_dashboard_api::test_category_counts_keep_decided_and_suggested_apart`, `test_dashboard_api::test_vulnerability_counts_confirmed_indicators_only_once_per_case`, `test_deadline_risk::test_windows_agree_with_the_countdown_shown_on_each_case`; *front end:* `shows deadline risk, with each number linked to its cases`, `shows AI suggestions apart from decided categories` |
| 2 | A handler gets `403` | `test_dashboard_api::test_a_handler_gets_403`; *front end:* `is told the dashboard is for team leads, and the API is not even asked` |
| 3 | My tenant only | `test_tenant_isolation::test_dashboard_and_its_filters_count_only_own_tenants_cases` |
| 4 | A number opens the matching cases | `test_dashboard_api::test_every_number_matches_the_list_it_links_to`, `test_dashboard_api::test_deadline_filters_return_the_right_cases`; *front end:* `opens the matching cases and asks the API for exactly those` |

## US-6: Personal data is redacted before it reaches the LLM

| # | Criterion | Proved by |
|---|---|---|
| 1 | Each kind of personal data → a typed placeholder | `test_redaction.py`: one test per kind (emails, cards, sort codes, accounts, phones, NI numbers, dates of birth, postcodes, names) |
| 2 | The same value → the same placeholder | `test_redaction::test_the_same_email_gets_the_same_placeholder`, `test_redaction::test_the_same_card_written_two_ways_is_one_placeholder`, `test_redaction::test_the_same_phone_with_and_without_country_code_is_one_placeholder`, `test_redaction::test_the_same_ni_number_written_two_ways_is_one_placeholder` |
| 3 | A "should NOT redact" case for each kind | `test_redaction::test_a_date_is_not_a_sort_code`, `test_redaction::test_amounts_and_other_numbers_are_not_account_numbers`, `test_redaction::test_a_long_number_that_fails_luhn_is_not_a_card`, and the other `..._not_...` / `..._are_kept` tests in the file |
| 4 | The original stays; the redacted text is stored as sent | `test_analysis_job_handler::test_only_redacted_text_reaches_the_model_and_it_is_stored_as_sent`, `test_llm_providers::test_sends_only_the_redacted_text_in_json_mode` |
| 5 | Redaction fails → no LLM call, `needs_human_review` | `test_analysis_job_handler::test_a_redaction_failure_never_calls_the_model`, `test_redaction::test_an_unexpected_failure_is_reported_as_a_redaction_error` |
| 6 | Logs never contain the complaint | `test_logging::test_logs_carry_ids_but_never_the_complaint_or_personal_data`, `test_messages_and_retry_policy::test_the_error_never_echoes_the_message_content`, `test_ai_output::test_the_rejection_reason_never_quotes_the_answer` |

## US-7: Tenant isolation

| # | Criterion | Proved by |
|---|---|---|
| 1 | Every tenant-owned table has an indexed, non-null `tenant_id` | `test_tenant_isolation::test_every_tenant_owned_table_has_an_indexed_non_null_tenant_id` (CI's `alembic check` proves the migrations match the models) |
| 2 | The tenant comes only from the authenticated user | `test_tenant_isolation::test_tenant_cannot_be_chosen_by_the_client` |
| 3 | Filtering in one place | `test_tenant_isolation::test_tenant_filtering_happens_only_in_the_repositories`, `test_tenant_isolation::test_repository_get_does_not_return_another_tenants_case`, `test_tenant_isolation::test_add_refuses_an_entity_from_another_tenant` |
| 4 | Another tenant's case → `404`, not `403` | `test_tenant_isolation::test_user_cannot_get_another_tenants_case_by_id` |
| 5 | One test per endpoint | `test_tenant_isolation`: list, audit trail, assign (both ways), dashboard; `test_case_review_api::test_another_tenant_cannot_decide_anything` (category, priority, indicators) |
| 6 | The worker loads by case id **and** tenant id | `test_analysis_job_handler::test_a_job_with_another_tenants_id_cannot_touch_the_case` |
| 7 | Demo data has at least two tenants with cases | `test_tenant_isolation::test_the_demo_data_has_two_tenants_with_cases_and_can_be_loaded_twice` |

## Non-functional requirements

| Area | Proved by |
|---|---|
| Logging | `test_logging::test_logs_carry_ids_but_never_the_complaint_or_personal_data` (every line is JSON, the same correlation id from intake through the relay to the worker, no complaint text or personal data), `test_cases_api::test_correlation_id_is_echoed_or_generated`, `test_job_consumer::test_the_handler_runs_under_the_jobs_correlation_id` |
| Validation | `test_cases_api::test_received_at_cannot_be_changed_after_intake` (every request body forbids unknown fields), `test_cases_api::test_create_case_rejects_invalid_input`, `test_messages_and_retry_policy::test_invalid_messages_are_rejected` |
| Secrets | `test_llm_providers::test_the_default_provider_is_the_fake_one`, `test_llm_providers::test_a_real_provider_without_a_key_fails_at_startup`, `test_llm_providers::test_a_real_provider_is_built_from_settings_and_the_key_stays_secret`; CI runs `pip-audit` and `npm audit` |
| Tests | CI: ruff, mypy, pytest on SQLite and on PostgreSQL + RabbitMQ, oxlint, tsc, Vitest, the nginx image, and the full Docker Compose stack |
| Time | `test_deadlines::test_deadlines_are_returned_in_utc`, `test_deadlines::test_naive_datetimes_are_refused`, `test_cases_api::test_create_case_returns_201_with_new_status_and_reference` (returned in UTC); *front end:* `shows UK time, whatever the computer is set to` |
