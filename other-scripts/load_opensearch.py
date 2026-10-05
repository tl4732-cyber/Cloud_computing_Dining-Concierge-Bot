import os

import boto3
import requests
from requests.auth import HTTPBasicAuth

ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"].rstrip("/")
auth = HTTPBasicAuth(os.environ["OPENSEARCH_USER"], os.environ["OPENSEARCH_PASSWORD"])
INDEX = "restaurants"

table = boto3.resource("dynamodb", region_name="us-east-1").Table("yelp-restaurants")


def create_index():
    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "RestaurantID": {"type": "keyword"},
                "Cuisine": {"type": "keyword"},
            }
        },
    }
    response = requests.put(f"{ENDPOINT}/{INDEX}", json=mapping, auth=auth, timeout=30)
    print("create index", response.status_code, response.text)


def bulk_body(items):
    lines = []
    for item in items:
        business_id = item.get("business_id")
        cuisine = item.get("cuisine")
        if not business_id or not cuisine:
            continue
        lines.append({"index": {"_index": INDEX, "_id": business_id}})
        lines.append({"RestaurantID": business_id, "Cuisine": cuisine})
    return "\n".join(__import__("json").dumps(line) for line in lines) + "\n"


def main():
    create_index()
    scanned = 0
    indexed = 0
    scan_kwargs = {}
    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        scanned += len(items)
        body = bulk_body(items)
        if body.strip():
            response = requests.post(
                f"{ENDPOINT}/_bulk",
                data=body,
                auth=auth,
                headers={"Content-Type": "application/x-ndjson"},
                timeout=60,
            )
            response.raise_for_status()
            if response.json().get("errors"):
                raise RuntimeError(response.text[:1000])
            indexed += body.count("\n") // 2
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    count = requests.get(f"{ENDPOINT}/{INDEX}/_count", auth=auth, timeout=30)
    print("scanned", scanned)
    print("indexed", indexed)
    print("count", count.status_code, count.text)


if __name__ == "__main__":
    main()