# User stories and acceptance criteria

The acceptance criteria use Given / When / Then. Each criterion maps to at least one automated test. The milestone tells you where it gets built.

**Roles:** `handler` (complaint handler), `team_lead`.
Every user belongs to exactly one tenant (client firm).

---

## US-1: Submit a complaint and see it as a case immediately

> As a **handler**, I can submit or import a complaint email (subject, body, sender, received time) and see it appear as a case immediately, while the AI analysis happens in the background.

**Milestones:** 2 (API), 4 (queue)

**Acceptance criteria**

1. **Given** I am an authenticated handler, **when** I POST a complaint with subject, body, sender email and received time, **then** I get `201 Created` with the case. The case has a human-readable reference (e.g. `CMP-2026-3F9A1C2B`), status `new`, and my tenant id.
2. The response comes back **without waiting for the AI**. The analysis is queued, not run inside the request.
3. **Given** a received time in the future, an empty body, or an invalid sender email, **when** I submit, **then** I get `422` with a field-level error, and no case is created.
4. **Given** I submit, **then** the case's `received_at` is the time I gave. If I gave none, it is the server time. It **cannot be changed afterwards**, because the deadlines depend on it.
5. **Given** a case was created, **then** exactly one analysis job is published to the queue with the case id, tenant id and a correlation id.
6. **Given** the queue is unavailable when the case is created, **then** the case is still saved and the failure is logged with the correlation id. The case can be re-queued later. *(Decided in milestone 4: a transactional outbox. The API never calls the broker; the relay keeps retrying until it is back.)*
7. **Given** I submit the same email twice with the same `external_message_id`, **then** the second request returns the existing case and does not create a duplicate.

---

## US-2: See the AI's suggestions with evidence

> As a **handler**, I see the AI's suggested category, a short summary, suggested priority, and any vulnerability indicators, each with the sentence that triggered it as evidence.

**Milestone:** 5

**Acceptance criteria**

1. **Given** the analysis finished successfully, **when** I open the case, **then** I see:
   - a **suggested category** from the fixed list (see [data-model.md](data-model.md))
   - a **summary** of at most 400 characters
   - a **suggested priority**: `low`, `medium`, `high` or `urgent`
   - zero or more **vulnerability indicators**
2. Each vulnerability indicator has a **type** (e.g. `bereavement`, `physical_illness`, `mental_health`, `financial_hardship`, `low_capability`), the FG21/1 **driver** it belongs to, and an **evidence quote**.
3. **The evidence quote must appear word for word in the (redacted) complaint text.** If it does not, the indicator is dropped and a warning is logged. The model may not invent evidence.
4. **Given** the analysis is still running, **then** the case shows status `analysing` and no suggestions. The rest of the case (body, deadlines) is still usable.
5. **Given** the model returns output that fails validation, **then** the worker retries **once**. **Given** it fails again, **then** the case goes to `needs_human_review` with the reason recorded. No partial suggestions are shown as if they were valid.
6. **Given** a complaint has any vulnerability indicator, **then** the suggested priority is at least `high`. This is a business rule in code, not left to the model.
7. Suggestions show which provider and model produced them (e.g. `fake`, `gpt-4o-mini`).

---

## US-3: Accept or override suggestions, with an audit trail

> As a **handler**, I can accept or override each suggestion, and the system records who changed what and when.

**Milestones:** 2 (audit table), 5 (decisions)

**Acceptance criteria**

1. **Given** a suggested category, **when** I accept it, **then** the case's final category equals the suggestion. An audit event records `category`, old value, new value, me, time, and `source = accepted_suggestion`.
2. **Given** a suggested category, **when** I override it with a different valid category, **then** the final category is my value and the audit event has `source = override`. The original suggestion is **kept**, not overwritten.
3. The same rules apply to **priority**.
4. **Given** a vulnerability indicator, **when** I confirm or reject it, **then** its decision is stored with me and the time, and an audit event is written. A rejected indicator stays visible as rejected and is not deleted.
5. **Given** I add a vulnerability indicator the AI missed, **then** it is stored with `source = handler` and its own evidence quote.
6. **Given** any change to a case, **then** an audit event is written **in the same database transaction** as the change. If either fails, neither is saved.
7. Audit events **cannot be edited or deleted** through the API. They have no update or delete endpoints.
8. **When** I view a case, **then** I can see its full audit trail, newest first.

---

## US-4: Always see the regulatory deadlines

> As a **handler**, I always see the case's regulatory deadlines and how many business days are left.

**Milestone:** 3

**Acceptance criteria**

1. **Given** a case, **then** it shows two deadlines, calculated from `received_at` in `Europe/London` time:
   - **SRC deadline**: close of business (17:00) on the **third business day following the day of receipt** (DISP 1.5.1R)
   - **Final response deadline**: end of the day **8 weeks (56 calendar days)** after receipt (DISP 1.6.2R)
2. Business days exclude Saturdays, Sundays and **UK bank holidays for the tenant's region** (default England and Wales).
3. **Given** received on Friday 2026-12-18, **then** the SRC deadline is Wednesday 2026-12-23 at 17:00.
4. **Given** received on Wednesday 2026-12-23, **then** the SRC deadline skips Christmas Day and Boxing Day (substitute day Monday 2026-12-28), so it is Wednesday 2026-12-30 at 17:00.
5. **Given** received on a Saturday, **then** the 3 business days count from Monday.
6. **Then** the case shows **business days remaining** until each deadline. **Given** a deadline has passed and the case is not resolved, **then** the value is negative and the case is marked **overdue**.
7. **Given** a case is resolved, **then** the deadlines stop counting down and the case shows whether it was resolved in time.
8. Deadline logic is a **pure function** (no database, no clock inside). "Now" is passed in as a parameter, so tests are deterministic.
9. Bank holiday data is **loaded from a local file** that can be refreshed from gov.uk. The app does not call gov.uk at runtime.

> **Verified 2026-10-01** against `https://www.gov.uk/bank-holidays.json` (england-and-wales): Christmas Day is 2026-12-25 (Friday). Boxing Day is the substitute day 2026-12-28 (Monday).

**Implementation decisions (milestone 3)**

- "Business days remaining" counts business days after today up to and including the deadline day: `0` means due today.
- A deadline missed earlier today (e.g. 18:00 against 17:00) counts as `-1`, so an overdue value is always negative.
- "Resolved in time" compares `resolved_at` with the SRC deadline when the resolution is an SRC, and with the final response deadline otherwise.
- If the bank holiday file does not cover a date, the deadline is **left empty and an error is logged**, never guessed. The case itself is still saved (US-1).

---

## US-5: Team lead dashboard

> As a **team lead**, I see a dashboard of cases close to breach, overdue cases, and counts by category and vulnerability flag.

**Milestone:** 7 (API endpoints can come earlier)

**Acceptance criteria**

1. **Given** I am a team lead, **then** I see:
   - **At risk**: open cases with **2 business days or fewer** left on their nearest deadline
   - **Overdue**: open cases past a deadline
   - **Counts by final category** (or suggested category, if not decided yet, shown differently)
   - **Counts by vulnerability type** (confirmed flags only)
2. **Given** I am a handler, **when** I call the dashboard endpoint, **then** I get `403`.
3. All numbers are **for my tenant only**.
4. **When** I click a number, **then** I see the matching cases.

---

## US-6: Personal data is redacted before it reaches the LLM

> As the **firm**, personal data is redacted before any text is sent to the LLM, and the original is stored only in our database.

**Milestone:** 5

**Acceptance criteria**

1. **Before** any LLM call, the text is redacted. Each item is replaced with a typed placeholder, numbered per complaint:
   - email addresses → `[EMAIL_1]`
   - UK phone numbers (mobile and landline, with or without +44 and spaces) → `[PHONE_1]`
   - card numbers (13–19 digits, with or without spaces/dashes, **passing a Luhn check**) → `[CARD_1]`
   - UK bank account numbers (8 digits) and sort codes (`12-34-56`) → `[ACCOUNT_1]`, `[SORT_CODE_1]`
   - UK postcodes → `[POSTCODE_1]`
   - the sender's name, and names after greetings or sign-offs ("Dear …", "Regards, …") → `[NAME_1]`
2. The same value gets the same placeholder throughout the text. If the same email appears twice, both become `[EMAIL_1]`.
3. There is a **unit test for each data type**, including at least one "should NOT redact" case. For example, a date like `12-03-2026` is not a sort code, and an amount like `£1,250.00` is not an account number.
4. The **original** complaint stays in the database. The **redacted** text sent to the model is also stored on the analysis record, so we can prove what left our system.
5. **Given** redaction throws an error, **then** the LLM is **not** called and the case goes to `needs_human_review`. We fail closed.
6. Logs never contain the original complaint body. They contain only ids and the correlation id.

> **BA note:** regex redaction of free-text names is imperfect. We say this honestly in the README. A production system would add an NER model (e.g. Presidio) and Azure OpenAI with data residency. This is a deliberate trade-off.

---

## US-7: Tenant isolation

> As a **platform**, each client firm is a tenant, and no user can ever see another tenant's cases.

**Milestone:** 2

**Acceptance criteria**

1. Every tenant-owned table has a non-null `tenant_id` column with an index.
2. The tenant is taken **only from the authenticated user**, never from the request body, query string or headers chosen by the client.
3. Tenant filtering happens **in one place**: a FastAPI dependency plus a query helper or repository base. Endpoints do not write their own `WHERE tenant_id = ...`.
4. **Given** a user of tenant A, **when** they GET a case of tenant B by id, **then** the response is `404`, not `403`. We do not reveal that the case exists.
5. **Given** a user of tenant A, **when** they list cases, update a case, or read the dashboard, **then** they never see tenant B data. There is one test per endpoint.
6. **Given** a worker job for a case, **then** the worker loads the case using **both** case id and tenant id from the message.
7. Seed data has **at least two tenants** with cases, so isolation can be demonstrated live.

---

## Non-functional requirements (all stories)

| Area | Requirement |
|---|---|
| Logging | Structured JSON logs. Every log line in the API and worker carries `correlation_id`, plus `tenant_id` and `case_id` where known. No complaint text or PII in logs. |
| Validation | All input validated by Pydantic. Unknown fields rejected. |
| Secrets | None in the repo; only `.env.example`. The app runs with no secrets at all, using the fake LLM provider. |
| Tests | Every feature ships with its tests. CI runs ruff, mypy and pytest. |
| Time | All timestamps stored in UTC (`timestamptz`). Shown in `Europe/London`. |
