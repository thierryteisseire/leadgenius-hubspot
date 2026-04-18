---
name: hubspot-leadgenius
description: Use this skill whenever the user asks to import, sync, migrate, or export leads from LeadGenius into HubSpot. This is the definitive guide and toolset for LeadGenius to HubSpot integration. Covers Private App setup, schema creation, rate-limit bypassing (using X-Admin-Key), JSON parsing for AI scores/emails/company descriptions, and batch upserts using the HubSpot v3 APIs.
---

# LeadGenius to HubSpot API Synchronization

This skill provides a comprehensive, agentic workflow for securely synchronizing thousands of highly enriched LeadGenius leads into HubSpot CRM. This pipeline utilizes advanced bypass headers and custom payload parsing to safely inject complex AI insights into native HubSpot custom properties.

## 1. Architecture & Design Principles

When acting on behalf of the user to synchronize leads, keep the following architecture principles in mind:

- **Global Rate Limit Bypass:** Standard LeadGenius pulls are heavily throttled. By supplying the Administrative Bypass Token (`LGP_MASTER_KEY`) via the `X-Admin-Key` header alongside the standard `X-API-Key`, rate-limiting is essentially disabled, allowing multi-thousand record synchronization streams.
- **`capture_all` Deconstruction:** LeadGenius frequently embeds highly valuable categorical data inside a raw string formatted as `:Key: Value | :Key: Value`. The Python integration natively regex-parses this field to safely extract properties such as the `Company Description` or direct mobile phone arrays.
- **Idempotency via Email Address:** All integrations strictly target the HubSpot Batch Upsert API utilizing the Lead `Email` as the deterministic `idProperty`. This guarantees that executing the sync millions of times will never cause duplicate record collisions in the CRM.

## 2. Prerequisite Setup

Before running operations, the environment must contain an `.env` file at the root of the user's workspace defining the following variables:

```env
# LeadGenius Credentials
LGP_API_KEY=your_standard_lg_token
LGP_MASTER_KEY=your_admin_bypass_token

# HubSpot Credentials
HUBSPOT_API_KEY=your_private_app_bearer_token 
```
> [!NOTE]
> *Agents: Use the `view_file` tool on the `.env` locally to verify these variables are securely populated before initiating heavy extraction runs.*

## 3. The CRM Schema (HubSpot Custom Properties)

To avoid heavily polluting the user's standard Hubspot tables, the execution engine dynamically builds a dedicated Property Group inside HubSpot named **`leadgenius_data`**. 

**Mapping Strategy Highlights:**
- **Scores as Integers:** Variables like `lg_ai_score` are intentionally type-cast heavily to native integers (e.g. `72` instead of `72.0`) to provide clean filtering mechanisms.
- **Emails Unpacked:** Natively nested objects inside `AiColdEmail` or similar JSON fields are aggressively string-formatted into standard carriage returns (`\n`) for optimal display inside HubSpot text areas.
- **Direct Phone Fallback:** `mobilephone` natively prioritizes direct line numbers extracted directly from the system over standard switchboard routes.

## 4. Execution Workflow

When the user asks to sync leads, use the primary integration layer.

**Step 1: Execute Synchronization Pipeline**
Run the core integration script from the skill directory. This handles the full multi-threaded payload extraction and batch push automatically:
```bash
python3 scripts/lg_full_to_hs.py
```

**Step 2: Monitor Terminal Telemetry**
- The script rapidly parses batches of 50 leads locally. 
- It dumps payloads sequentially to a local `/tmp/lg_full_leads_cache.json` memory block to decouple network retrieval failures from HubSpot injections.
- Validates the total yield against HubSpot's API `crm/v3/objects/contacts/batch/upsert`.

## 5. SDR View Configuration 

Since HubSpot's V3 API restricts the generation of shared UX-driven Saved Views directly externally, you MUST advise the user to perform this manual step to fully extract the value of the synchronization:

1. Navigate to **Contacts > Add View > Create New View** ("SDR Priority Pipeline").
2. Insert custom columns sequentially: `LG AI Score`, `Mobile Phone`, `LG Justification`, `LG Recommendation`, `Lead Status`.
3. Inform users to edit their **Record Customization** (Sidebar) natively to pin the `leadgenius_data` Property Group right at the top for maximal speed during aggressive outreach.
