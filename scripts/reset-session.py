#!/usr/bin/env python3
"""Reset the Fluent web session: delete the current opencode session and create a new one.

Usage:
    python3 scripts/reset-session.py [--host HOST] [--user USER] [--password PASS]

The script prints the new session ID. The web UI will auto-create a new
session when you refresh the page (or click "Nova sessió").
"""
import argparse, json, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

DEFAULTS = {
    "host": "http://127.0.0.1:4100/api",
    "user": "opencode",
    "password": "8cYfFtlZhAu8NwTg",
}

def api(host, user, password, path="", method="GET", body=None):
    import base64
    url = f"{host}/{path}" if path else host
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    cred = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    with urlopen(req) as res:
        return json.loads(res.read())

def main():
    p = argparse.ArgumentParser(description="Reset the Fluent web session")
    p.add_argument("--host", default=DEFAULTS["host"])
    p.add_argument("--user", default=DEFAULTS["user"])
    p.add_argument("--password", default=DEFAULTS["password"])
    args = p.parse_args()

    try:
        sessions = api(args.host, args.user, args.password, "session")
    except HTTPError as e:
        print(f"error: connection failed ({e.code})", file=sys.stderr)
        sys.exit(1)

    for s in sessions:
        sid = s.get("id") or s.get("info", {}).get("id")
        if not sid:
            continue
        try:
            api(args.host, args.user, args.password, f"session/{sid}", "DELETE")
            print(f"deleted: {sid}")
        except HTTPError as e:
            print(f"warning: could not delete {sid}: {e}", file=sys.stderr)

    new = api(args.host, args.user, args.password, "session", "POST", {"title": "Fluent"})
    new_id = new.get("id") or new.get("info", {}).get("id")
    print(f"new session: {new_id}")

if __name__ == "__main__":
    main()
