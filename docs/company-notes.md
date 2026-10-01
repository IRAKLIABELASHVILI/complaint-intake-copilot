# Company notes: Contact Web

Checked on 2026-10-01 against the public website. Each claim is marked:

- **Confirmed**: stated on the website (page linked).
- **Job description**: comes from the Full Stack Developer job description, not the website.
- **Assumption**: my own inference. Not a fact about the company.

## Company

| Claim | Status | Source |
|---|---|---|
| UK customer operations / outsourcing company, founded April 2023 | Confirmed | [Home](https://contactweb.co.uk) |
| Delivery in the UK (Banbury, Oxfordshire HQ), South Africa (Cape Town) and Georgia (Tbilisi) | Confirmed | [Home](https://contactweb.co.uk), [Complaints handling](https://contactweb.co.uk/services/complaints-handling) |
| Services: customer service, sales and lead generation, back-office, collections and credit control, complaints handling, recruitment and resourcing | Confirmed | [Home](https://contactweb.co.uk) |
| Sectors: financial services, legal, healthcare, utilities | Partly confirmed | Complaints page mentions financial services products (PPI, motor finance, packaged accounts) and Ofgem / Ofwat / Ofcom frameworks. Legal and healthcare were not seen on the pages checked. |
| ISO 27001 and Cyber Essentials certified, GDPR compliance by design | Confirmed | [Home](https://contactweb.co.uk), [Technology](https://contactweb.co.uk/technology) |
| Positioning: "AI where it adds value. People where they matter most." | Confirmed | [Home](https://contactweb.co.uk) |

## AI products

| Product | What the website says | Status |
|---|---|---|
| **QAI** (Quality AI) | 100% call scoring, no sampling bias; checks interactions against compliance frameworks; flags vulnerable customers; finds coaching opportunities | Confirmed, [Technology](https://contactweb.co.uk/technology) |
| **KAI** (Knowledge AI) | Gives agents accurate answers during live interactions; connects to CRM and telephony | Confirmed, [Technology](https://contactweb.co.uk/technology) |
| **CAI** (Complaints AI) | Categorises, prioritises and supports complaint resolution; automates regulatory deadline tracking; FCA- and FOS-aligned | Confirmed, [Technology](https://contactweb.co.uk/technology) |
| **ConnexAI** | Omnichannel platform (voice, email, chat, social, messaging); real-time analytics, workforce management, SLA monitoring | Confirmed, [Technology](https://contactweb.co.uk/technology) |
| **Outcome AI** | AI-assisted complaints and case management platform | **Job description only.** Not found on the home, technology or complaints pages, nor by a web search. Treat it as the internal or product name of the platform behind CAI (assumption). |

**Integrations listed on the website:** Salesforce, HubSpot, Zendesk, Genesys, NICE CXone, Five9, Avaya, Microsoft Teams, Twilio, Stripe. NICE CXone, Five9, Avaya, Teams and Stripe were missing from my original brief, so I added them here.

## Complaints handling service

From [Complaints handling](https://contactweb.co.uk/services/complaints-handling) (confirmed):

1. Assess volumes, root causes and compliance position.
2. Train a specialist team on products and regulatory requirements.
3. Log, triage and allocate within agreed SLAs, **with audit trails**.
4. Root cause analysis to find systemic issues.
5. Monthly management information (volumes, resolution rates, trends).

Other claims on the page: end-to-end lifecycle up to FOS referral, redress calculation and payment, "98% complaints resolved within FCA timescales".

**What this means for the project:** steps 3 and 5 are exactly what this project demonstrates. Step 3 maps to intake, triage, deadlines and audit trail. Step 5 maps to the team lead dashboard. Redress calculation and FOS referral are **out of scope**.

## Engineering stack (job description)

| Today | Direction |
|---|---|
| Python, Flask, SQLAlchemy, Jinja | FastAPI + Pydantic, typed OpenAPI contracts |
| PostgreSQL + Alembic | Multi-tenant PostgreSQL, pgvector later |
| BPMN / DMN workflows | Queue-driven, horizontally scalable workers (Azure Service Bus) |
| Docker on Azure, GitHub Actions | Infrastructure as code, OpenTelemetry |
| pytest, Playwright | React + TypeScript + Vite |
| | Azure OpenAI with personal data protected before it reaches a model |

## Regulatory facts used in this project

| Rule | What it says | Source |
|---|---|---|
| DISP 1.5.1R | The time limit rules do not apply to a complaint resolved **by close of business on the third business day following the day on which it is received**. | [FCA Handbook DISP 1.5](https://handbook.fca.org.uk/handbook/disp1/disp1s5) |
| DISP 1.5.4R | A complaint resolved that way gets a **summary resolution communication** (SRC), which must mention the right to refer to the FOS. | [FCA Handbook DISP 1.5](https://handbook.fca.org.uk/handbook/disp1/disp1s5) |
| DISP 1.6.2R | **By the end of eight weeks after receipt**, the firm must send a final response, or a written explanation of why it cannot yet and when it expects to. | [FCA Handbook DISP 1.6](https://handbook.fca.org.uk/handbook/disp1/disp1s6) |
| FCA FG21/1 | Guidance on fair treatment of vulnerable customers. It names four drivers of vulnerability: **health, life events, resilience, capability**. | FCA FG21/1 (used for the vulnerability taxonomy) |

**Out of scope:** payment services and e-money complaints. They have a shorter limit of 15 business days, or 35 in exceptional cases. A real system would need a per-complaint-type rule set, so the deadline engine is designed to make adding one easy.

## Assumptions

1. **Business day:** not a Saturday, Sunday or bank holiday in the relevant part of the UK. A tenant's region defaults to England and Wales. Holidays come from the gov.uk bank holidays feed.
2. **"Eight weeks after receipt"** is 56 calendar days from the date of receipt, ending at the end of that day, UK time.
3. **Time zone:** all deadlines are calculated in `Europe/London` and stored in UTC.
4. **Receipt time:** a complaint that arrives on a non-business day, or after close of business, is still "received" that day. The rule says "the third business day *following* the day on which it is received", so the 3 days count from the next business day either way.
