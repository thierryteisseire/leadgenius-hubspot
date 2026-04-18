---
name: hubspot-leadgenius
description: Export LeadGenius leads and import them into HubSpot CRM with custom AI properties, Property Groups, and automated scripts. Covers Private App setup, property creation, data mapping, and batch imports using HubSpot v3 APIs.
---

# LeadGenius → HubSpot Import Guide

> How to export leads from LeadGenius and import them into a HubSpot portal, with custom properties for all AI insights and enrichment data.

---

## Table of Contents

0. [Overview](#0-overview)
1. [Prerequisites](#1-prerequisites)
2. [Creating the HubSpot Private App](#2-creating-the-hubspot-private-app)
3. [Exporting from LeadGenius](#3-exporting-from-leadgenius)
4. [LeadGenius CSV Field Reference](#4-leadgenius-csv-field-reference)
5. [Creating Custom Properties inside HubSpot](#5-creating-custom-properties-inside-hubspot)
6. [Importing & Updating Contacts](#6-importing-updating-contacts)
7. [Creating Saved Views](#7-creating-saved-views)
8. [Complete Automated Script](#8-complete-automated-script)

---

## 0. Overview

### What This Does

```text
LeadGenius CSV  →  HubSpot Contacts
 120 columns        with custom AI properties
                    + Property Group (LeadGenius AI)
                    + Custom Saved Views
```

### Architecture

LeadGenius exports a CSV with up to **120 columns** per lead. Most HubSpot portals have a standard schema. This guide bridges the gap by:

1. **Creating a dedicated Property Group** (`leadgenius_data`) to prevent cluttering the CRM.
2. **Creating 17 custom properties** on the Contact object to hold AI and enrichment data.
3. **Importing contacts** utilizing the HubSpot CRM Contacts API (deduplicating by email).
4. **Updating contacts** with AI analysis data into dedicated custom properties.
5. **Configuring Saved Views / Lists** that surface AI Score and Seniority.

### API Strategy Summary

| Operation | API Used | Why |
|-----------|----------|-----|
| Authentication | Private App Token (Bearer) | Modern authentication, no OAuth UI hassle |
| Create Property Group | CRM Properties v3 | Groups custom LG fields in the sidebar |
| Create properties | CRM Properties v3 | Adds schema definitions programmatically |
| Batch Insert/Update | CRM Contacts v3 Batch | Deduplicates by email natively in batches of 100 |

---

## 1. Prerequisites

### Software

```bash
pip3 install requests python-dotenv
```

### Environment File

Create `.env` in your working directory:

```env
# HubSpot
HUBSPOT_ACCESS_TOKEN=pat-na1-...
```

---

## 2. Creating the HubSpot Private App

A **Private App** provides the Access Token required to run integrations securely against your specific portal.

1. Click the **⚙️ Settings** icon in the main navigation bar.
2. In the left sidebar, navigate to **Integrations** > **Private Apps**.
3. Click **Create private app**.
4. Basic Info: Name it **"LeadGenius Sync"**.
5. Switch to the **Scopes** tab and grant:
   - `crm.objects.contacts.read`
   - `crm.objects.contacts.write`
   - `crm.schemas.contacts.read`
   - `crm.schemas.contacts.write`
6. Click **Create app** and copy your **Access Token**. Store it in your `.env`.

---

## 3. Exporting from LeadGenius

Use the LeadGenius UI to select leads, click **Export**, and select **CSV**. Name the file descriptively (e.g., `hubspot_leads_import.csv`).

---

## 4. LeadGenius CSV Field Reference

### Standard Lead Fields (→ HubSpot Default Properties)

| LeadGenius Column | HubSpot Property | Notes |
|-------------------|------------------|-------|
| `First Name` | `firstname` | |
| `Last Name` | `lastname` | Required |
| `Title` | `jobtitle` | |
| `Email` | `email` | Primary unique identifier |
| `Phone Number` | `phone` | |
| `Company Name` | `company` | |
| `Industry` | `industry` | |
| `Estimated Num Employees` | `numemployees` | |
| `Country` | `country` | |
| `City` | `city` | |

### AI Insight Fields (→ HubSpot Custom Properties)

| LeadGenius Column | HubSpot Property Internal Name | Type |
|-------------------|--------------------------------|------|
| `Ai Score Value` | `lg_ai_score` | number |
| `Ai Lead Score Score` | `lg_lead_score` | number |
| `Ai Qualification` | `lg_qualification` | string (text) |
| `Ai Score Justification` | `lg_justification` | string (multiline) |
| `Ai Next Action` | `lg_next_action` | string (multiline) |
| `Ai Cold Email` | `lg_cold_email` | string (multiline) |
| `Ai Linkedin Connect` | `lg_linkedin_connect` | string (multiline) |
| `Ai Decision Maker Role` | `lg_decision_role` | string (text) |
| `Is Likely To Engage` | `lg_likely_engage` | string (text) |

### Enrichment Fields

| LeadGenius Column | HubSpot Property Internal Name | Type |
|-------------------|--------------------------------|------|
| `Linkedin Url` | `lg_linkedin_url` | string (text) |
| `Company Linkedin Url` | `lg_company_linkedin` | string (text) |
| `Seniority` | `lg_seniority` | string (text) |
| `Enrichment5 Engagement Rate` | `lg_engagement_rate` | number |
| `Lead Id` | `lg_lead_id` | string (text) |

---

## 5. Creating Custom Properties inside HubSpot

All properties are prefixed with `lg_`. We will create a property group called `leadgenius_data` first.

### Create Property Group

```python
import requests, os
from dotenv import load_dotenv
load_dotenv()

headers = {'Authorization': f"Bearer {os.getenv('HUBSPOT_ACCESS_TOKEN')}", 'Content-Type': 'application/json'}

group_payload = {
    "name": "leadgenius_data",
    "displayOrder": -1,
    "label": "LeadGenius AI Data"
}
requests.post('https://api.hubapi.com/crm/v3/properties/contacts/groups', headers=headers, json=group_payload)
```

### Create Properties

```python
PROPERTIES = [
    {"name": "lg_ai_score", "label": "LG AI Score", "type": "number", "fieldType": "number", "groupName": "leadgenius_data"},
    {"name": "lg_qualification", "label": "LG Qualification", "type": "string", "fieldType": "text", "groupName": "leadgenius_data"},
    {"name": "lg_justification", "label": "LG Justification", "type": "string", "fieldType": "textarea", "groupName": "leadgenius_data"},
    {"name": "lg_next_action", "label": "LG Next Action", "type": "string", "fieldType": "textarea", "groupName": "leadgenius_data"},
    {"name": "lg_cold_email", "label": "LG Cold Email", "type": "string", "fieldType": "textarea", "groupName": "leadgenius_data"},
    {"name": "lg_likely_engage", "label": "LG Likely to Engage", "type": "string", "fieldType": "text", "groupName": "leadgenius_data"},
    {"name": "lg_linkedin_url", "label": "LG LinkedIn URL", "type": "string", "fieldType": "text", "groupName": "leadgenius_data"},
    {"name": "lg_seniority", "label": "LG Seniority", "type": "string", "fieldType": "text", "groupName": "leadgenius_data"},
    {"name": "lg_lead_id", "label": "LG Lead ID", "type": "string", "fieldType": "text", "groupName": "leadgenius_data"}
]

for prop in PROPERTIES:
    r = requests.post('https://api.hubapi.com/crm/v3/properties/contacts', headers=headers, json=prop)
    if r.status_code == 201:
        print(f"✅ Prop created: {prop['name']}")
    elif "already exists" in r.text:
        print(f"⏭️ Prop skipped: {prop['name']}")
    else:
        print(f"❌ Error: {r.text}")
```

---

## 6. Importing & Updating Contacts

With HubSpot's Batch API, you can seamlessly **Upsert** leads by using their Email address as the fallback identifier.

```python
import csv, requests, os

headers = {'Authorization': f"Bearer {os.getenv('HUBSPOT_ACCESS_TOKEN')}", 'Content-Type': 'application/json'}

def safe_str(val): return str(val).strip() if val else ""

with open('hubspot_leads_import.csv', 'r') as f:
    rows = list(csv.DictReader(f))

# Chunk into batches of 100 maximum
batch_size = 100
for i in range(0, len(rows), batch_size):
    chunk = rows[i:i+batch_size]
    
    inputs = []
    for row in chunk:
        if not row.get('Email'): continue # Contacts must have emails
        
        inputs.append({
            "idProperty": "email",
            "id": safe_str(row.get('Email')),
            "properties": {
                "firstname": safe_str(row.get('First Name')),
                "lastname": safe_str(row.get('Last Name')) or "Unknown",
                "jobtitle": safe_str(row.get('Title')),
                "company": safe_str(row.get('Company Name')),
                "lg_ai_score": safe_str(row.get('Ai Score Value')),
                "lg_qualification": safe_str(row.get('Ai Qualification')),
                "lg_justification": safe_str(row.get('Ai Score Justification')),
                "lg_cold_email": safe_str(row.get('Ai Cold Email')),
                "lg_linkedin_url": safe_str(row.get('Linkedin Url'))
            }
        })
        
    payload = { "inputs": inputs }
    
    r = requests.post('https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert', headers=headers, json=payload)
    if r.status_code in [200, 201, 204]:
        print(f"✅ Batch {i} to {i+len(chunk)} upserted successfully.")
    else:
        print(f"❌ Batch error: {r.text}")
```

---

## 7. Creating Saved Views

Since API creation of Lists/Views can be complex depending on tiers:
1. Go to **Contacts**.
2. Click **Add view** -> **Create new view** ("LeadGenius AI Leads").
3. Click **Edit Columns**: 
   - Add `LG AI Score`, `LG Qualification`, `LG Seniority`.
4. Add **Advanced Filters**: `LG AI Score` is known.
5. Sort by `LG AI Score` High to Low.

## Summary

You have successfully mapped all Custom AI outputs into HubSpot natively, grouped perfectly in the sidebar, scaling batch upserts without UI data-loader constraints.
