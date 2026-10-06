import base64
import http.client
import json
import os
import random
import socket
import ssl

import boto3

sqs = boto3.client("sqs")
ses = boto3.client("ses")
restaurants_table = boto3.resource("dynamodb").Table("yelp-restaurants")
state_table = boto3.resource("dynamodb").Table("user-search-state")

QUEUE_URL = os.environ["SQS_QUEUE_URL"]
ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"].rstrip("/")
SENDER = os.environ["SENDER_EMAIL"]


def opensearch_connection(host):
    context = ssl.create_default_context()
    addresses = []
    for info in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM):
        ip = info[4][0]
        if ip not in addresses:
            addresses.append(ip)
    # 100.x answers from a laptop but does not return data to Lambda.
    addresses.sort(key=lambda ip: ip.startswith("100."))
    last_error = None
    for ip in addresses:
        try:
            raw = socket.create_connection((ip, 443), timeout=5)
            return context.wrap_socket(raw, server_hostname=host)
        except OSError as error:
            last_error = error
    raise RuntimeError(f"Could not connect to {host}: {last_error}")


def opensearch_ids(cuisine):
    endpoint = os.environ["OPENSEARCH_ENDPOINT"].rstrip("/")
    host = endpoint.removeprefix("https://").split("/")[0]
    token = base64.b64encode(
        f"{os.environ['OPENSEARCH_USER']}:{os.environ['OPENSEARCH_PASSWORD']}".encode()
    ).decode()
    payload = json.dumps({"size": 50, "query": {"term": {"Cuisine": cuisine}}}).encode()
    ssock = opensearch_connection(host)
    connection = http.client.HTTPSConnection(host, 443, timeout=10)
    try:
        connection.sock = ssock
        connection.request(
            "POST",
            "/restaurants/_search",
            body=payload,
            headers={
                "Host": host,
                "Content-Type": "application/json",
                "Authorization": f"Basic {token}",
            },
        )
        response = connection.getresponse()
        raw_body = response.read().decode()
    finally:
        connection.close()
    if response.status != 200:
        raise RuntimeError(f"OpenSearch error {response.status}: {raw_body}")
    body = json.loads(raw_body)
    ids = [hit["_source"]["RestaurantID"] for hit in body["hits"]["hits"]]
    return random.sample(ids, min(3, len(ids)))


def format_email(request, restaurants):
    lines = [
        f"Hello! Here are my {request['cuisine']} restaurant suggestions for {request['number_of_people']} people, for {request['dining_time']}:",
        "",
    ]
    for number, restaurant in enumerate(restaurants, start=1):
        lines.append(f"{number}. {restaurant['name']}, located at {restaurant['address']}")
    lines.extend(["", "Enjoy your meal!"])
    return "\n".join(lines)


def send_email(request, restaurants):
    ses.send_email(
        Source=SENDER,
        Destination={"ToAddresses": [request["email"]]},
        Message={
            "Subject": {"Data": f"{request['cuisine']} restaurant suggestions"},
            "Body": {"Text": {"Data": format_email(request, restaurants)}},
        },
    )


def save_state(request, restaurants):
    if not request.get("session_id"):
        return
    state_table.put_item(Item={
        "userId": request["session_id"],
        "location": request["location"],
        "cuisine": request["cuisine"],
        "dining_time": request["dining_time"],
        "number_of_people": request["number_of_people"],
        "email": request["email"],
        "restaurants": [
            {"name": restaurant["name"], "address": restaurant["address"]}
            for restaurant in restaurants
        ],
    })


def lambda_handler(event, context):
    received = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=0)
    messages = received.get("Messages") or []
    if not messages:
        return {"status": "empty"}

    message = messages[0]
    request = json.loads(message["Body"])
    if request.get("cuisine"):
        request["cuisine"] = request["cuisine"].strip().title()

    if request.get("reuse_previous"):
        saved = state_table.get_item(Key={"userId": request["session_id"]}).get("Item")
        if not saved:
            raise RuntimeError("No saved recommendations for this user")
        send_email(saved, saved["restaurants"])
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
        return {"status": "resent"}

    restaurants = []
    for business_id in opensearch_ids(request["cuisine"]):
        item = restaurants_table.get_item(Key={"business_id": business_id}).get("Item")
        if item:
            restaurants.append(item)

    if not restaurants:
        raise RuntimeError(f"No restaurants found for {request['cuisine']}")

    send_email(request, restaurants)
    save_state(request, restaurants)
    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
    return {"status": "sent", "count": len(restaurants)}