# Companies & Associations — the correct, safe way

Importing contacts alone leaves them with only a `company` text field — no company object,
no primary association, no company-level rollups. `scripts/lg_companies_associations.py`
adds the company layer. This doc explains the rules it follows and the failure it prevents.

## The one rule that matters most

> **HubSpot batch endpoints (`batch/upsert`, `batch/create`, `batch/read`) do NOT return
> results in input order.** Never correlate a batch result to its input by list index.
> Always correlate by a key the API echoes back (email, a unique id, or the company
> key/domain).

### The failure this prevents

A naive importer collected ids positionally and then paired them by index:

```python
ids.extend([r.get("id") for r in body.get("results", [])])   # response order!
...
if cid and contact_ids[i]:                                   # input i vs. response-ordered id
    pairs.append({"from": {"id": contact_ids[i]}, "to": {"id": cid},
                  "types": [{"associationTypeId": 1}]})       # 1 = PRIMARY
```

Because results come back reordered, contact A was associated to contact B's company and
that company was marked **primary**. On one production portal this mis-associated ~10,400
contacts and created ~8,000 junk companies. Two separate positional maps (companies and
contacts) compounded the scramble.

### The fix (what the script does)

- `resolve_ids_by_key()` reads the `idProperty` value echoed on each result
  (`email`, `lg_company_key`) and builds a `{key -> id}` map. If a result omits the
  property, it falls back to a `batch/read` by object id — never to list position.
- Companies are keyed by `lg_company_key = "domain:<domain>"` (or `"name:<name>"` only when
  there is no domain). Domain is the dedup anchor; this avoids the duplicate-company
  explosion.
- Associations are built by map lookup (`contact_id_by_email[email]`,
  `company_id_by_key[key]`), then the primary company is set with an idempotent
  `PUT /crm/v4/objects/contacts/{id}/associations/companies/{companyId}` with
  `associationTypeId: 1`. PUT creates-or-relabels without duplicating; if the contact
  already has that company as primary, it is skipped.

## Idempotency

Re-running must not add a second company or a second primary. The script checks the current
primary and only writes when it differs. A clean re-run reports
`associations set primary: 0 (unchanged=N)`.

## Audit against company domain, not email domain

`hs_audit_primary.py` compares the primary company to the row's **Company Domain**. The
person's email domain can legitimately differ (subsidiary / local entity, e.g. an
`@schueco.com` contact whose company is `Schüco France` / `schuco.fr`). Auditing on email
domain alone produces false "WRONG" results.

## Endpoints used

| Purpose | Endpoint |
|---|---|
| Upsert companies (dedup by `lg_company_key`) | `POST /crm/v3/objects/companies/batch/upsert` |
| Resolve ids that didn't echo the key | `POST /crm/v3/objects/{type}/batch/read` |
| Read a contact's companies | `GET /crm/v4/objects/contacts/{id}/associations/companies` |
| Set/relabel primary (idempotent) | `PUT /crm/v4/objects/contacts/{id}/associations/companies/{companyId}` |

Avoid the legacy `/crm/v4/associations/contact/company/batch/create` (singular types) — it
has no idempotency and encourages index-based pairing.
