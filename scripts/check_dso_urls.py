#!/usr/bin/env python3
"""Check that every predefined DSO URL still serves a valid SEC-Energy document.

Dead DSO links are the integration's most common silent failure: the user just
gets an error during setup. This checker finds them before users do.

Usage:
    python3 check_dso_urls.py            # check all, print only problems + summary
    python3 check_dso_urls.py --all      # print every DSO with its status
    python3 check_dso_urls.py --json     # machine readable, for the PM bot
    python3 check_dso_urls.py --only Flawil

Network only; nothing is written to the repository.
"""

import ast
import concurrent.futures
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = os.environ.get("SEC_ENERGY_REPO", str(
    Path.cwd() if (Path.cwd() / "custom_components/sec_energy/config_flow.py").is_file()
    else Path(__file__).resolve().parents[1]))
CONFIG_FLOW = os.path.join(REPO_ROOT, "custom_components/sec_energy/config_flow.py")
UA = "Mozilla/5.0 (X11; Linux x86_64) HomeAssistant/sec-energy health-check"
TIMEOUT = 25
WORKERS = 10


def load_dsos():
    """Read PREDEFINED_DSOS without importing Home Assistant."""
    if not os.path.exists(CONFIG_FLOW):
        raise SystemExit(
            f"config_flow.py not found at {CONFIG_FLOW}\n"
            "Clone the repo first: git clone "
            "https://github.com/marcelloceschia/ha-ch-energy.git "
            f"{REPO_ROOT}"
        )
    tree = ast.parse(open(CONFIG_FLOW, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit("PREDEFINED_DSOS not found")


def check(item, year=None):
    year = year or datetime.now(ZoneInfo("Europe/Zurich")).year
    name, source = item
    url = source.get(year) if isinstance(source, dict) else source
    result = {"name": name, "url": url, "ok": False, "status": None, "detail": ""}
    if url is None:
        result.update(unavailable=True, detail=f"no configured URL for {year}")
        return result
    # The list also holds the pseudo-entry "Custom / Other": "custom".
    if not url.startswith(("http://", "https://")):
        result["ok"] = True
        result["detail"] = "skipped (not a URL)"
        result["skipped"] = True
        return result
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            result["status"] = resp.status
            raw = resp.read(2_000_000)
        try:
            doc = json.loads(raw)
        except ValueError:
            result["detail"] = "response is not JSON"
            return result
        tariffs = doc.get("tariffs")
        if not isinstance(tariffs, list) or not tariffs:
            result["detail"] = "JSON without non-empty tariffs array"
            return result
        years = sorted({str(t.get("startDate", ""))[:4] for t in tariffs} - {""})
        result["years"] = years
        result["ok"] = True
        result["detail"] = f"{len(tariffs)} tariffs, years {','.join(years)}"
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["detail"] = f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        result["detail"] = f"URL error: {str(exc.reason)[:80]}"
    except Exception as exc:
        result["detail"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    return result


def main():
    argv = sys.argv[1:]
    dsos = load_dsos()
    if "--only" in argv:
        needle = argv[argv.index("--only") + 1].lower()
        dsos = {k: v for k, v in dsos.items() if needle in k.lower()}
        if not dsos:
            raise SystemExit("no DSO matches that filter")

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(check, sorted(dsos.items())))

    broken = [r for r in results if not r["ok"] and not r.get("unavailable")]
    if "--json" in argv:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        sys.exit(1 if broken else 0)

    unavailable = [r for r in results if r.get("unavailable")]
    checked = [r for r in results if not r.get("skipped") and not r.get("unavailable")]
    if "--all" in argv:
        for r in results:
            mark = "OK " if r["ok"] else "FAIL"
            print(f"{mark} {r['name'][:52]:52} {r['detail']}")
    else:
        for r in broken:
            print(f"FAIL {r['name'][:52]:52} {r['detail']}")

    for r in unavailable:
        print(f"UNAVAILABLE {r['name']}: {r['detail']}")
    print(f"\n{len(checked) - len(broken)}/{len(checked)} gesund, "
          f"{len(broken)} defekt, {len(unavailable)} ohne aktuelle Jahres-URL")
    if broken:
        sys.exit(1)


if __name__ == "__main__":
    main()
