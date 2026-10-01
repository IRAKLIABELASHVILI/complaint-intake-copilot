# Brief: Complaint Intake Copilot

## The problem

Complaint handlers in FCA-regulated firms receive complaints by email. Every complaint must be:

1. **Logged** as a case with a reliable receipt time.
2. **Categorised** and **prioritised**.
3. **Checked for signs of customer vulnerability** (FCA FG21/1: health, life events, resilience, capability).
4. **Resolved within the regulatory deadlines** (DISP 1.5 and 1.6):
   - a summary resolution communication by close of the third business day after receipt, **or**
   - a final response within eight weeks.

Doing this by hand is slow and inconsistent. Each of these failures is a real regulatory and customer-outcome risk:

- **A missed vulnerability signal** means a customer in a bad situation is treated like everyone else.
- **A missed deadline** is a breach.
- **An inconsistent category** makes root cause analysis and management information unreliable.

## What the product does

Complaint Intake Copilot is a small slice of an AI-assisted complaints platform:

> **The AI suggests, the handler decides, and the system remembers who decided what.**

1. **Intake.** A complaint email becomes a case immediately. The receipt time is fixed and the deadlines are calculated.
2. **Analysis in the background.** A worker redacts personal data, asks an LLM for a category, summary, priority and vulnerability indicators, then validates the answer.
3. **Evidence.** Every vulnerability indicator links to the exact sentence that triggered it. If the model cannot point to evidence, the indicator is rejected.
4. **Human decision.** The handler accepts or overrides every suggestion. Each change goes to the audit trail.
5. **Deadlines.** Always visible, in business days, using UK bank holidays.
6. **Oversight.** A team lead sees cases close to breach, overdue cases, and the mix of categories and vulnerability flags.

## Users

| User | Goal | Main screens |
|---|---|---|
| **Complaint handler** | Work their queue quickly and correctly; never miss a vulnerable customer or a deadline | Case list, case detail |
| **Team lead** | See risk early: what is close to breach, what is overdue, where vulnerability is concentrated | Dashboard |
| **The firm (compliance)** | Prove that personal data is protected, decisions are made by people, and every change is audited | Audit trail, redaction tests, tenant isolation tests |

## Principles (BA position)

These come from the business problem, not from the technology. If a feature breaks one of them, I will push back on it.

1. **The AI never makes the decision.** It only makes suggestions. A case's category, priority and vulnerability flags are only "final" once a person has accepted or overridden them. This matches Contact Web's own message: people make the judgement calls.
2. **No evidence, no flag.** A vulnerability indicator without a quoted sentence from the complaint is worse than useless. The handler cannot check it, and it trains them to ignore flags.
3. **A failure must be visible.** If the model returns invalid output twice, the case goes to "needs human review". The system never guesses.
4. **Personal data never reaches the model.** Names, emails, phone numbers, account and card numbers, and addresses are redacted first. The original is stored only in our database.
5. **Tenants never see each other.** One client firm can never read another client firm's cases. This is enforced in one place and proven by tests.
6. **Deadlines come from the rules, not the model.** The deadline engine is pure, deterministic code with tests. The LLM is never asked when a deadline is.

## In scope

- Email intake (API and seed import). Fields: subject, body, sender, received time.
- Background AI analysis through a queue, with retries and a dead-letter queue.
- Suggestions: category, short summary, priority, vulnerability indicators with evidence.
- Accept or override, with an audit trail.
- DISP deadlines (3-business-day SRC and 8-week final response), using UK bank holidays.
- Team lead dashboard.
- Multi-tenancy, PII redaction, seeded demo users, around 15 fictional complaints.

## Out of scope (deliberately)

- Letters, call recordings, attachments and OCR. The website mentions these channels, but email alone shows the full pipeline.
- Redress calculation, FOS referral, final response letter drafting.
- Payment services / e-money deadlines (15 business days).
- Real authentication (SSO, OAuth). Seeded demo users with a simple token are enough to show tenant isolation.
- BPMN / DMN workflow engine. Case status is a simple, explicit state machine.
- CRM integrations (Salesforce, Zendesk and others).

## How we know it works (success criteria)

- `docker compose up` starts everything. Seeded cases are visible and analysed **without any API key**, thanks to the fake LLM provider.
- Test suites prove: tenant isolation, each PII type is redacted, deadline calculation around weekends and bank holidays, and worker idempotency, retry and dead-letter behaviour.
- CI (ruff, mypy, pytest) is green on every push.
- A recruiter understands the README in one minute.

## Data

Only **synthetic, clearly fictional** complaints are used. Names, emails, phone numbers and account numbers in the seed data are invented. Phone numbers come from Ofcom's drama ranges (for example 07700 900xxx). Card numbers come from published test ranges.
