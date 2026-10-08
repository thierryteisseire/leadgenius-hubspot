"""Audit each contact's PRIMARY company against the source CSV.

Compares the HubSpot primary company (associationTypeId 1) to the company expected from
the source row (its Company Domain, else Company Name). Reports OK / WRONG / NO_PRIMARY /
NO_CONTACT and writes detail to hs_audit_primary_report.json.

Compare against the row's COMPANY DOMAIN, not the person's email domain: for subsidiaries
and local entities the two differ legitimately (e.g. an @schueco.com email whose company
is "Schüco France" / schuco.fr).

Usage:
  python hs_audit_primary.py <file.csv>
  python hs_audit_primary.py <file.csv> --limit 50
"""
import argparse, csv, json, os, re, sys, time, urllib.request, urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN") or os.getenv("HUBSPOT_API_KEY")
if not TOKEN:
    try:
        for line in open(".env", encoding="utf-8"):
            if line.strip().lower().startswith("hubspot-app="):
                TOKEN = line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
if not TOKEN:
    print("ERROR: set HUBSPOT_ACCESS_TOKEN in .env"); sys.exit(1)

BASE = "https://api.hubapi.com"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_last = [0.0]


def req(method, path, body=None, retries=6):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
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
                time.sleep(2 * (attempt + 1)); continue
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw
        except Exception:
            time.sleep(2 * (attempt + 1))
    return 0, None


def lc(row, *names):
    low = {k.lower(): v for k, v in row.items()}
    for n in names:
        v = low.get(n.lower())
        if v:
            return str(v).strip()
    return ""


def root(d):
    return (d or "").lower().split(".")[0]


def expected_domain(row):
    d = lc(row, "Company Domain", "companyDomain").lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].strip()
    if d and "." in d:
        return d
    email = lc(row, "Email").lower()
    if EMAIL_RE.match(email):
        return email.split("@")[1]
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv_file, encoding="utf-8-sig")))
    if a.limit:
        rows = rows[:a.limit]

    counts = {"OK": 0, "WRONG": 0, "NO_PRIMARY": 0, "NO_CONTACT": 0, "NO_COMPANY_IN_SOURCE": 0}
    detail = []
    for row in rows:
        email = lc(row, "Email").lower()
        if not EMAIL_RE.match(email):
            continue
        dom = expected_domain(row)
        name = lc(row, "Company Name", "companyName")
        if not dom and not name:
            counts["NO_COMPANY_IN_SOURCE"] += 1
            continue
        st, b = req("POST", "/crm/v3/objects/contacts/search",
                    {"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
                     "properties": ["email"], "limit": 1})
        if st >= 300 or not b.get("results"):
            counts["NO_CONTACT"] += 1
            continue
        cid = b["results"][0]["id"]
        st, a2 = req("GET", f"/crm/v4/objects/contacts/{cid}/associations/companies?limit=100")
        prim = None
        for x in (a2.get("results", []) if st < 300 else []):
            if any(t.get("typeId") == 1 for t in x.get("associationTypes", [])):
                prim = str(x["toObjectId"])
        if not prim:
            counts["NO_PRIMARY"] += 1
            detail.append({"email": email, "expectedDomain": dom, "verdict": "NO_PRIMARY"})
            continue
        st, co = req("GET", f"/crm/v3/objects/companies/{prim}?properties=domain,name")
        cdom = (co.get("properties", {}).get("domain") or "").lower()
        cname = co.get("properties", {}).get("name") or ""
        ok = (dom and root(cdom) == root(dom)) or (not dom and name and name.lower() in cname.lower())
        if ok:
            counts["OK"] += 1
        else:
            counts["WRONG"] += 1
            detail.append({"email": email, "expectedDomain": dom, "primaryCompany": cname,
                           "primaryDomain": cdom, "verdict": "WRONG"})

    json.dump({"counts": counts, "detail": detail[:500]},
              open("hs_audit_primary_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("AUDIT:", counts)
    print("Report -> hs_audit_primary_report.json")


if __name__ == "__main__":
    main()
