if not WATCHLIST_FILE.exists():
    raise FileNotFoundError(
        f"Missing watchlist: {WATCHLIST_FILE}"
    )

with WATCHLIST_FILE.open(
    "r",
    encoding="utf-8",
) as file:
    data = json.load(file)

return [
    stock
    for stock in data.get("stocks", [])
    if stock.get("enabled", True)
]
try:

    response = session.get(
        url,
        params=params,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.json()

except Exception as exc:

    log.warning(
        "Request failed: %s | %s",
        url,
        exc,
    )

    return None
  result = []

for item in items:

    if item and item not in result:
        result.append(item)

return result
