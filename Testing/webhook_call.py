import requests
import uuid


URL = "http://localhost:7000/webhook-test/b7063177-edb9-479e-95e2-bf4974daa477"


payload = {
    "action": "continue",
    "username": "test_user",
    "user_id": "f495ffa0-f93e-4ac8-a150-e1d4021f2a67",
    "conversation_id": "8409aebb-2e0f-4fa3-a141-6f803a777df1",
    "message_id": str(uuid.uuid4()),
    "message": "I am still feeling overwhelmed and it is becoming difficult to manage."
}


try:
    response = requests.post(
        URL,
        json=payload,
        timeout=30,
    )

    print("Status Code:", response.status_code)
    print("Response:")

    try:
        print(response.json())
    except ValueError:
        print(response.text)

except requests.exceptions.RequestException as exc:
    print("Request failed:")
    print(exc)