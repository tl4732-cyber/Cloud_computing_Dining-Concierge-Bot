import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import requests

API_KEY = os.environ["YELP_API_KEY"]
TABLE_NAME = "yelp-restaurants"
CUISINES = ["Chinese", "Japanese", "Italian", "Indian", "Mexican", "Korean"]
LOCATION = "Manhattan, NY"
SEARCH_URL = "https://api.yelp.com/v3/businesses/search"

table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE_NAME)
seen_ids = set()


def decimal_or_none(value):
    if value is None:
        return None
    return Decimal(str(value))


def search(cuisine, offset):
    response = requests.get(
        SEARCH_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        params={
            "term": f"{cuisine} restaurants",
            "location": LOCATION,
            "limit": 50,
            "offset": offset,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("businesses", [])


def to_item(business, cuisine):
    location = business.get("location") or {}
    coordinates = business.get("coordinates") or {}
    address = ", ".join(location.get("display_address") or [])
    return {
        "business_id": business["id"],
        "name": business.get("name", ""),
        "address": address,
        "coordinates": {
            "latitude": decimal_or_none(coordinates.get("latitude")),
            "longitude": decimal_or_none(coordinates.get("longitude")),
        },
        "review_count": business.get("review_count", 0),
        "rating": decimal_or_none(business.get("rating")),
        "zip_code": location.get("zip_code", ""),
        "cuisine": cuisine,
        "insertedAtTimestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    stored_by_cuisine = {cuisine: 0 for cuisine in CUISINES}

    with table.batch_writer() as batch:
        for cuisine in CUISINES:
            for offset in (0, 50, 100, 150):
                businesses = search(cuisine, offset)
                for business in businesses:
                    business_id = business.get("id")
                    if not business_id or business_id in seen_ids:
                        continue
                    seen_ids.add(business_id)
                    batch.put_item(Item=to_item(business, cuisine))
                    stored_by_cuisine[cuisine] += 1
                time.sleep(0.3)
                if len(businesses) < 50:
                    break

    print("Stored per cuisine:", stored_by_cuisine)
    print("Unique restaurants:", len(seen_ids))


if __name__ == "__main__":
    main()