import json

def lambda_handler(event, context):
    body = {
        "messages": [
            {
                "type": "unstructured",
                "unstructured": {
                    "id": "1",
                    "text": "I'm still under development. Please come back later.",
                    "timestamp": "2026-10-04T00:00:00Z"
                }
            }
        ]
    }

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,POST"
        },
        "body": json.dumps(body)
    }