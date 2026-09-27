"""Thin Apify client: start an actor, wait, hand back the dataset rows.

Only the three calls this project needs. A failed pull raises PullError and
never leaves a half-written store behind.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class PullError(RuntimeError):
    """The source could not be pulled. Expected — LinkedIn blocks sometimes."""


def _request(method: str, url: str, token: str, body: dict | None = None, timeout: int = 60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        detail = err.read()[:400].decode("utf-8", "replace")
        raise PullError(f"Apify returned {err.code} for {method} {url.split('?')[0]}: {detail}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise PullError(f"Could not reach Apify: {err}") from err


def run_actor(
    actor: str,
    payload: dict,
    token: str,
    *,
    max_items: int,
    max_cost_usd: float,
    poll_seconds: int = 5,
    timeout_seconds: int = 900,
    on_status=None,
    on_items=None,
) -> tuple[list[dict], float | None]:
    """Run an actor to completion; return its dataset rows and what it cost.

    max_cost_usd is enforced by Apify itself, so a runaway actor cannot eat the
    month's credit even if this process is killed. on_items(n) is called whenever
    the number of rows collected so far changes (for a progress bar).
    """
    query = urllib.parse.urlencode({"maxItems": max_items, "maxTotalChargeUsd": max_cost_usd})
    run = _request("POST", f"{API}/acts/{actor.replace('/', '~')}/runs?{query}", token, payload)["data"]
    run_id = run["id"]

    deadline = time.monotonic() + timeout_seconds
    status, count = run["status"], 0
    while status not in TERMINAL:
        if time.monotonic() > deadline:
            _request("POST", f"{API}/actor-runs/{run_id}/abort", token)
            raise PullError(f"{actor} still running after {timeout_seconds}s — aborted.")
        time.sleep(poll_seconds)
        run = _request("GET", f"{API}/actor-runs/{run_id}", token)["data"]
        if run["status"] != status:
            status = run["status"]
            if on_status:
                on_status(status)
        if on_items:
            try:
                now = _request("GET", f"{API}/datasets/{run['defaultDatasetId']}", token)["data"]["itemCount"]
            except (PullError, KeyError, TypeError):
                continue  # a missed count only makes the bar lag; never fail the pull over it
            if now != count:
                count = now
                on_items(count)

    if status != "SUCCEEDED":
        raise PullError(
            f"{actor} finished as {status}. Run log: https://console.apify.com/actors/runs/{run_id}"
        )

    # Some actors refuse work (e.g. a free-plan run limit) yet still finish as
    # SUCCEEDED with an empty dataset. Their status message is the only sign.
    message = (run.get("statusMessage") or "").lower()
    if any(word in message for word in ("limit exceeded", "upgrade", "not allowed")):
        raise PullError(f"{actor} refused the run: {run.get('statusMessage')}. "
                        f"Run log: https://console.apify.com/actors/runs/{run_id}")

    dataset = run["defaultDatasetId"]
    items = _request("GET", f"{API}/datasets/{dataset}/items?clean=true&limit={max_items}", token)
    cost = run.get("usageTotalUsd")
    return items if isinstance(items, list) else [], cost


def account(token: str) -> dict:
    return _request("GET", f"{API}/users/me", token)["data"]


def usage(token: str) -> tuple[float, float | None]:
    """(spent this billing cycle, monthly limit) in USD.

    A single run's usageTotalUsd lags behind and often reads 0, so anything
    reporting cost to the user should ask the account, not the run.
    """
    data = _request("GET", f"{API}/users/me/usage/monthly", token)["data"]
    spent = (data.get("totalUsageCreditsUsdAfterVolumeDiscount")
             or data.get("totalUsageCreditsUsd") or 0.0)
    limit = (account(token).get("plan") or {}).get("maxMonthlyUsageUsd")
    return round(float(spent), 4), limit
