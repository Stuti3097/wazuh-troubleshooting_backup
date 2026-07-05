"""
Generic helpers for calling the Wazuh indexer's REST API with auth already
applied, so use cases don't each re-type the same
`curl -k -s -u USER:PASS URL` boilerplate by hand.

Reusable by any future use case that needs to hit the indexer API
(cluster health, cat indices, cat shards, etc.).
"""

import json
from executor import run_command
from config import INDEXER_USERNAME, INDEXER_PASSWORD, INDEXER_URL


def indexer_api_get(endpoint, extra_args=""):
    """
    GET a path from the indexer's REST API.

    `endpoint` should start with "/", e.g. "/_cluster/health".
    `extra_args` lets callers pass extra curl flags/query params if needed.
    Returns the raw response text (empty string on failure).
    """
    url = f"{INDEXER_URL}{endpoint}"
    cmd = f"curl -k -s -u {INDEXER_USERNAME}:'{INDEXER_PASSWORD}' {extra_args} {url}"
    return run_command(cmd) or ""


def indexer_api_get_json(endpoint, extra_args=""):
    """
    Same as indexer_api_get, but parses the response as JSON.

    Returns (parsed_json, raw_text). If parsing fails, parsed_json is None
    and raw_text is preserved so the caller can still show it to the user
    for diagnosis (e.g. "the indexer isn't reachable, here's the raw error").
    """
    raw = indexer_api_get(endpoint, extra_args)
    try:
        return json.loads(raw), raw
    except (ValueError, TypeError):
        return None, raw
