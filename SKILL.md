---
name: hubspot-leadgenius
description: Use this skill whenever the user asks to import, sync, migrate, or export leads from LeadGenius into HubSpot. This is the definitive guide and toolset for LeadGenius to HubSpot integration. Covers Private App setup, schema creation, rate-limit bypassing (using X-Admin-Key), json parsing for AI scores/emails/company descriptions, and batch upserts using the HubSpot v3 APIs.
---

# LeadGenius → HubSpot Import API Pipeline

A robust, fully automated API pipeline for seamlessly synchronizing highly enriched LeadGenius leads (and their deep JSON AI insights) natively into HubSpot CRM.

## Architecture

This skill provides the automated workflow for pulling thousands of leads dynamically from LeadGenius and pushing them into HubSpot without rate-limiting constraints using an admin bypass natively structured in Python.

1. **`scripts/lg_full_to_hs.py`**: The main execution engine.
   - Bypasses LeadGenius rate limits using the `X-Admin-Key` header.
   - Natively unpacks the deep `.data` JSON responses and deeply nested dictionaries (e.g. `capture_all`).
   - Specifically targets numerical cleansing for AI scores, array parsing for AI-generated Cold Emails, and native mapping for organizational data like `lg_company_description` and `mobilephone`.
   - Automates the creation of 45+ custom `lg_` Properties under a unified `leadgenius_data` Property Group natively in HubSpot.
   - Performs High-Volume Batch Upserts on HubSpot, matching leads implicitly on their emails (and safely POSTing non-email leads securely).

## Prerequisites

Ensure your working directory contains an `.env` file with the following tokens:

```env
LGP_API_KEY=your_standard_lg_token
LGP_MASTER_KEY=your_x_admin_key_for_unlimited_speed
HUBSPOT_API_KEY=your_private_app_bearer_token
```

## Running the Sync

To seamlessly upgrade your CRM and sync full environments in one swift action:

```bash
python3 scripts/lg_full_to_hs.py
```

### Script Execution Flow:
1. **Schema Integrity:** Scans HubSpot and automatically creates/verifies the custom 45-property CRM Schema natively.
2. **Global Pool Fetch:** Dynamically contacts LeadGenius to grab every single Lead Object ID inside your Campaign/Partition iteratively.
3. **High-Speed Cache Download:** Loops all IDs over `https://api.leadgenius.app/api/automation/leads/{lid}` completely ignoring rate limits by substituting `LGP_MASTER_KEY` under the `X-Admin-Key` header.
4. **CRM Upsert:** Deduplicates and uploads objects natively in 100-batch arrays to `api.hubapi.com/crm/v3/objects/contacts/batch/upsert`.

## Visual Dashboard Integration

Since programmatically building views is restricted by HubSpot's UI framework, ensure your SDRs configure their table manually:
1. Navigate to **HubSpot > Contacts > Add View**
2. Add columns: `LG AI Score`, `LG Justification`, `LG Recommendation`, `Mobile Phone`.
3. Save the view for the entire team to enable lightning-fast lead processing!
