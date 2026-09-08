"""Read-only public API evidence for industry research; never a strategy input.

Run with an explicit output directory. Existing output files are never replaced.
No account credentials, signed requests, or trading endpoints are used.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import urllib.request

REQUESTS = {
    "coingecko_global": ("https://api.coingecko.com/api/v3/global", None),
    "defillama_chains": ("https://api.llama.fi/v2/chains", None),
    "hyperliquid_context": ("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"}),
    "hyperliquid_predicted_fundings": ("https://api.hyperliquid.xyz/info", {"type": "predictedFundings"}),
    "hyperliquid_perp_dexs": ("https://api.hyperliquid.xyz/info", {"type": "perpDexs"}),
    "robinhood_stock_assets": ("https://api.robinhood.com/rhj/assets", None),
}


def capture(item: tuple) -> tuple:
    name, (url, body) = item
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    record = {"name": name, "url": url, "request_body": body, "requested_at_utc": started,
              "classification": "public_api_snapshot_diagnostic_only"}
    try:
        request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                        headers={"User-Agent": "IndustryResearch/1.0", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            record.update(http_status=response.status, response_date=response.headers.get("Date"),
                          content_type=response.headers.get("Content-Type"), payload=json.loads(raw),
                          response_sha256=hashlib.sha256(raw).hexdigest())
        record["status"] = "captured_not_independently_audited"
    except Exception as error:
        record.update(status="unavailable", error=str(error))
    record["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return name, record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if any(args.output_dir.glob("*.json")):
        raise SystemExit("Output already contains JSON evidence; select a new directory.")
    manifest = {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "use": "industry_context_only_not_live_arbitrage_or_accepted_market_dataset", "files": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for name, record in executor.map(capture, REQUESTS.items()):
            path = args.output_dir / f"{name}.json"
            contents = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            with path.open("x", encoding="utf-8") as handle:
                handle.write(contents)
            manifest["files"].append({"file": path.name, "status": record["status"],
                                      "sha256": hashlib.sha256(contents.encode()).hexdigest()})
            print(json.dumps({"source": name, "status": record["status"], "file": str(path)}))
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
