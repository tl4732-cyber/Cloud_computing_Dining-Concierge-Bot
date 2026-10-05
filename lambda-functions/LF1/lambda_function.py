import json
import os

import boto3

sqs = boto3.client("sqs")
state_table = boto3.resource("dynamodb").Table("user-search-state")
QUEUE_URL = os.environ["SQS_QUEUE_URL"]


def get_slot(slots, name):
    slot = (slots or {}).get(name)
    if not slot or not slot.get("value"):
        return None
    value = slot["value"]
    return value.get("interpretedValue") or value.get("originalValue")


def close(intent, message):
    return {
        "sessionState": {
            "dialogAction": {"type": "Close"},
            "intent": {
                "name": intent["name"],
                "slots": intent.get("slots") or {},
                "state": "Fulfilled",
            },
        },
        "messages": [{"contentType": "PlainText", "content": message}],
    }


def delegate(intent):
    return {
        "sessionState": {
            "dialogAction": {"type": "Delegate"},
            "intent": {
                "name": intent["name"],
                "slots": intent.get("slots") or {},
                "state": "InProgress",
            },
        }
    }


def elicit_slot(intent, slot_name, message):
    slots = intent.get("slots") or {}
    slots[slot_name] = None
    return {
        "sessionState": {
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot_name},
            "intent": {
                "name": intent["name"],
                "slots": slots,
                "state": "InProgress",
            },
        },
        "messages": [{"contentType": "PlainText", "content": message}],
    }


def previous_search(user_id):
    return state_table.get_item(Key={"userId": user_id}).get("Item")


def same_search(previous, location, cuisine):
    if not previous or not previous.get("restaurants"):
        return False
    return (
        "manhattan" in (location or "").lower()
        and "manhattan" in previous.get("location", "").lower()
        and cuisine
        and cuisine.lower() == previous.get("cuisine", "").lower()
    )


def queue(payload):
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload))


def handle_dining(event):
    intent = event["sessionState"]["intent"]
    slots = intent.get("slots") or {}
    user_id = event["sessionId"]
    location = get_slot(slots, "Location")
    cuisine = get_slot(slots, "Cuisine")

    if location and "manhattan" not in location.lower():
        return elicit_slot(
            intent,
            "Location",
            f"Sorry, I can't fulfill requests for {location}. Please enter a valid location.",
        )

    if location and cuisine and same_search(previous_search(user_id), location, cuisine):
        answer = (get_slot(slots, "SameRecommendation") or "").lower()
        if answer in {"yes", "yeah", "yep", "sure"}:
            queue({"reuse_previous": True, "session_id": user_id, "location": location, "cuisine": cuisine})
            return close(intent, "I'll send you the same recommendations as last time.")
        if answer not in {"no", "nope"}:
            return elicit_slot(
                intent,
                "SameRecommendation",
                f"You asked for {cuisine} in {location} last time. Would you like the same recommendations as last time?",
            )

    if event["invocationSource"] == "DialogCodeHook":
        return delegate(intent)

    queue({
        "location": location,
        "cuisine": cuisine,
        "dining_time": get_slot(slots, "DiningTime"),
        "number_of_people": get_slot(slots, "NumberOfPeople"),
        "email": get_slot(slots, "Email"),
        "session_id": user_id,
    })
    return close(intent, "You're all set. Expect my suggestions shortly! Have a good day.")


def lambda_handler(event, context):
    intent_name = event["sessionState"]["intent"]["name"]
    intent = event["sessionState"]["intent"]

    if intent_name == "GreetingIntent":
        return close(intent, "Hi there, how can I help?")
    if intent_name == "ThankYouIntent":
        return close(intent, "You're welcome.")
    if intent_name == "DiningSuggestionsIntent":
        return handle_dining(event)

    return close(intent, "Sorry, I didn't understand that.")