import json
from datetime import datetime, timezone

import boto3

lex = boto3.client("lexv2-runtime")

LEX_BOT_ID = "PUJJ6MTDYQ"
LEX_BOT_ALIAS_ID = "QPNVECYBMF"
LEX_LOCALE_ID = "en_US"


def response(messages):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
        },
        "body": json.dumps({"messages": messages}),
    }


def text_message(text):
    return {
        "type": "unstructured",
        "unstructured": {
            "id": "1",
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def lambda_handler(event, context):
    body = event.get("body") or "{}"
    if isinstance(body, str):
        body = json.loads(body)

    incoming = (body.get("messages") or [{}])[0]
    unstructured = incoming.get("unstructured") or {}
    user_text = (unstructured.get("text") or "").strip()
    session_id = unstructured.get("id") or "dining-session"

    if not user_text:
        return response([text_message("Please type a message.")])

    try:
        lex_response = lex.recognize_text(
            botId=LEX_BOT_ID,
            botAliasId=LEX_BOT_ALIAS_ID,
            localeId=LEX_LOCALE_ID,
            sessionId=session_id,
            text=user_text,
        )
    except Exception as error:
        print(error)
        return response([text_message("The bot is unavailable right now. Please try again.")])

    replies = []
    for message in lex_response.get("messages") or []:
        content = message.get("content")
        if content:
            replies.append(text_message(content))

    if not replies:
        replies.append(text_message("Sorry, I didn't understand that."))

    return response(replies)