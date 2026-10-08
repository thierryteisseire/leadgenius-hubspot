# Remediation playbook — repair an already-corrupted portal

Use this when contacts already show the wrong or multiple companies (symptom of a prior
index-based import). Do **not** just re-import on top — remediate first, then import with
`lg_companies_associations.py`. Every step is reversible with a JSON backup.

The order matters. Work from safest to least safe.

## 1. Measure the blast radius

For every contact with a corporate email, compare the primary company's domain to the
expected company (from source). Count mismatches and companies created in the bad import's
time window (e.g. a single day), especially those with **no domain** (the parasite
signature).

## 2. Flip the primary (safe, reversible)

For each mismatched contact, if the correct company is already associated (just not
primary), re-point the primary to it with
`PUT /crm/v4/objects/contacts/{id}/associations/companies/{companyId}` (`associationTypeId
1`). Back up the previous primary id per contact before changing it. Do NOT delete anything
yet. Verify a sample (and ideally re-scan the whole portal) before continuing.

> Note: the contact's `associatedcompanyid` property is recomputed asynchronously — allow a
> few seconds / poll before asserting success.

## 3. Remove parasite associations (reversible)

Drive this off the **live portal state**, not the import log, so it covers every affected
contact. For each contact, remove each NON-primary company association where the company
was created in the bad-import window AND its domain does not match the contact's expected
company. Keep the primary and keep legitimately-domained secondaries. Archive the link with
`POST /crm/v4/associations/contacts/companies/batch/archive`, body shape:

```json
{"inputs":[{"from":{"id":"<contactId>"},"to":[{"id":"<companyId>"}]}]}
```

(The `to` field is an **array**.) Back up every removed `(contactId, companyId)` pair so it
can be re-created.

## 4. Fix contacts whose correct company was never associated

Some contacts have only wrong companies attached — nothing to flip to. Match the correct
company by **email domain** (more reliable than name), reuse an existing company or create
one with that domain, associate it and set primary, then remove the old parasite primary.
Use an in-run cache keyed by domain so multiple contacts sharing a domain reuse one freshly
created company (avoids duplicates while the search index lags).

## 5. Archive orphaned parasite companies (least reversible — do last)

After contacts are fixed, archive the companies created in the bad window that have **no
domain and no remaining contact associations**:
`POST /crm/v3/objects/companies/batch/archive` with `{"inputs":[{"id":"..."}]}`. Keep any
company still referenced by a contact. Save the archived ids.

## 6. Verify end state

Re-scan the whole portal: primary-company-correct count should be ~100% and parasite
associations 0. Spot-check known examples by name.

## Rollback

Each step writes a backup JSON. To undo, re-apply the previous primary (step 2/4) or
re-create the removed associations (step 3) with the same PUT/create calls, and
un-archive companies via `.../companies/{id}` restore if needed.

## Prevention

The root cause is index-based correlation in the importer. After remediating, only import
with the corrected `lg_companies_associations.py` (see companies-and-associations.md). If
the old index-based script is re-run, the corruption returns.
