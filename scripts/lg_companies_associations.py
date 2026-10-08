"""Create companies and the correct PRIMARY contact->company association in HubSpot.

This complements lg_to_hs.py (which upserts contacts only). It:
  1. Upserts a company per distinct employer, keyed by DOMAIN (lg_company_key =
     "domain:<domain>"), falling back to name only when no domain exists.
  2. Associates each contact to its company and marks that company PRIMARY
     (associationTypeId 1), idempotently.

CRITICAL CORRECTNESS RULE
-------------------------
HubSpot batch endpoints DO NOT return results in input order. We NEVER pair a contact to
a company by list index. We correlate every batch result to its input by a key the API
echoes back (email / company domain), and we build associations via map lookups. Pairing
by index is exactly what previously attached contacts to the wrong company and marked it
primary. See references/companies-and-associations.md.

Input: the same CSV used by lg_to_hs.py. Expected columns (case-insensitive, extra columns
ignored): Email, Company Name, Company Domain (optional), Linkedin Url (optional).

Env (.env in the working directory): HUBSPOT_ACCESS_TOKEN=pat-...

Usage:
  python lg_companies_associations.py <file.csv>
  python lg_companies_associations.py <file.csv> --limit 50
"""
import argparse, csv, json, os, re, sys, time, urllib.request, urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN") or os.getenv("HUBSPOT_API_KEY")
if not TOKEN:
    # also support a `.env` line of the form hubspot-app=pat-...
    try:
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line.lower().startswith("hubspot-app="):
                TOKEN = line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
if not TOKEN:
    print("ERROR: set HUBSPOT_ACCESS_TOKEN in .env")
    sys.exit(1)

BASE = "https://api.hubapi.com"
GROUP = "leadgenius_data"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PRIMARY = [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1}]
_last = [0.0]


def req(method, path, body=None, retries=6):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for attempt in range(retries):
        gap = time.time() - _last[0]
        if gap < 0.15:
            time.sleep(0.15 - gap)
        _last[0] = time.time()
        r = urllib.request.Request(url, data=data, method=method)
        r.add_header("Authorization", "Bearer " + TOKEN)
        r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if e.code == 429 or e.code >= 500:
                time.sleep(2 * (attempt + 1)); last = raw; continue
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw
        except Exception as e:
            last = str(e); time.sleep(2 * (attempt + 1))
    return 0, last


def lc(row, *names):
    """Case-insensitive column getter."""
    low = {k.lower(): v for k, v in row.items()}
    for n in names:
        v = low.get(n.lower())
        if v:
            return str(v).strip()
    return ""


def domain_from(row):
    d = lc(row, "Company Domain", "companyDomain").lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].strip()
    if d and "." in d:
        return d
    email = lc(row, "Email").lower()
    if EMAIL_RE.match(email):
        dom = email.split("@")[1]
        free = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "yahoo.fr",
                "wanadoo.fr", "orange.fr", "free.fr", "laposte.net", "icloud.com"}
        if dom not in free:
            return dom
    return ""


def company_key(row):
    d = domain_from(row)
    if d:
        return ("domain", d)
    n = lc(row, "Company Name", "companyName")
    if n:
        return ("name", re.sub(r"\s+", " ", n).lower())
    return None


def ensure_company_props():
    # Ensure the lg_company_key unique property exists (dedup anchor).
    st, b = req("GET", "/crm/v3/properties/companies")
    existing = {p["name"] for p in b.get("results", [])} if st < 300 else set()
    if "lg_company_key" not in existing:
        req("POST", "/crm/v3/properties/companies/groups", {"name": GROUP, "label": "LeadGenius AI Data"})
        req("POST", "/crm/v3/properties/companies",
            {"name": "lg_company_key", "label": "LG Company Key", "type": "string",
             "fieldType": "text", "groupName": GROUP, "hasUniqueValue": True})


def resolve_ids_by_key(object_type, id_prop, results):
    """Map results to input keys via the echoed id property, never by index."""
    out, missing = {}, []
    for r in results:
        rid = r.get("id")
        key = (r.get("properties") or {}).get(id_prop)
        if key is not None:
            out[str(key).lower() if id_prop == "email" else str(key)] = rid
        elif rid is not None:
            missing.append(rid)
    for i in range(0, len(missing), 100):
        chunk = missing[i:i + 100]
        st, b = req("POST", f"/crm/v3/objects/{object_type}/batch/read",
                    {"inputs": [{"id": str(x)} for x in chunk], "properties": [id_prop]})
        if st < 300:
            for r in b.get("results", []):
                key = (r.get("properties") or {}).get(id_prop)
                if key is not None:
                    out[str(key)] = r.get("id")
    return out


def chunks(seq, n=100):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv_file, encoding="utf-8-sig")))
    if a.limit:
        rows = rows[:a.limit]
    rows = [r for r in rows if EMAIL_RE.match(lc(r, "Email").lower())]
    print(f"rows with email: {len(rows)}")

    ensure_company_props()

    # 1) distinct companies -> upsert by lg_company_key, keyed result map
    comp_inputs = {}
    for r in rows:
        k = company_key(r)
        if not k:
            continue
        keystr = f"{k[0]}:{k[1]}"
        if keystr in comp_inputs:
            continue
        props = {"lg_company_key": keystr, "name": lc(r, "Company Name", "companyName") or k[1]}
        if k[0] == "domain":
            props["domain"] = k[1]
        # Upsert inputs require BOTH idProperty and the id (its value).
        comp_inputs[keystr] = {"idProperty": "lg_company_key", "id": keystr, "properties": props}

    company_id_by_key = {}
    for chunk in chunks(list(comp_inputs.values())):
        st, b = req("POST", "/crm/v3/objects/companies/batch/upsert", {"inputs": chunk})
        if st < 300:
            company_id_by_key.update(resolve_ids_by_key("companies", "lg_company_key", b.get("results", [])))
        else:
            print("  company upsert error:", str(b)[:200])
    print(f"companies upserted: {len(company_id_by_key)}")

    # 2) contact ids by email (correlated by echoed email, not index)
    contact_id_by_email = {}
    cinputs = [{"idProperty": "email", "id": lc(r, "Email").lower(),
                "properties": {"email": lc(r, "Email").lower()}} for r in rows]
    for chunk in chunks(cinputs):
        st, b = req("POST", "/crm/v3/objects/contacts/batch/upsert", {"inputs": chunk})
        if st < 300:
            contact_id_by_email.update(resolve_ids_by_key("contacts", "email", b.get("results", [])))
        else:
            print("  contact lookup error:", str(b)[:200])

    # 3) set primary association idempotently
    made = unchanged = errors = 0
    for r in rows:
        email = lc(r, "Email").lower()
        cid = contact_id_by_email.get(email)
        k = company_key(r)
        comp = company_id_by_key.get(f"{k[0]}:{k[1]}") if k else None
        if not cid or not comp:
            continue
        st, a2 = req("GET", f"/crm/v4/objects/contacts/{cid}/associations/companies?limit=100")
        if st < 300 and any(str(x.get("toObjectId")) == str(comp) and
                            any(t.get("typeId") == 1 for t in x.get("associationTypes", []))
                            for x in a2.get("results", [])):
            unchanged += 1
            continue
        st, _ = req("PUT", f"/crm/v4/objects/contacts/{cid}/associations/companies/{comp}", PRIMARY)
        if st < 300:
            made += 1
        else:
            errors += 1
    print(f"associations set primary: {made} (unchanged={unchanged}, errors={errors})")


if __name__ == "__main__":
    main()
