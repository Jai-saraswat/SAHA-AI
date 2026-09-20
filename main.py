import os
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / "Database" / ".env"

load_dotenv(ENV_FILE)

WEBHOOK_URL = os.getenv("SAHA_WEBHOOK_URL")


def send_to_saha(payload):
    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()


def display_conversations(conversations):
    print("\nYour conversations:\n")

    if not conversations:
        print("No existing conversations.")
        return

    for index, conversation in enumerate(conversations, start=1):
        topic = conversation.get("topic") or "Untitled conversation"
        print(f"{index}. {topic}")


def main():
    if not WEBHOOK_URL:
        raise ValueError("SAHA_WEBHOOK_URL is not configured.")

    print("================================")
    print("           SAHA")
    print("================================")

    username = input("\nUsername: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    result = send_to_saha(
        {
            "action": "list",
            "username": username,
        }
    )

    if not result.get("success", True):
        print("\nError:", result)
        return

    conversations = result.get("conversations", [])

    display_conversations(conversations)

    print("\nN. Start a new conversation")

    while True:
        choice = input("\nChoose a conversation: ").strip()

        if choice.lower() == "n":
            conversation_id = None
            break

        if choice.isdigit():
            index = int(choice) - 1

            if 0 <= index < len(conversations):
                conversation_id = conversations[index]["conversation_id"]
                break

        print("Invalid choice. Please select a conversation number or N.")

    if conversation_id:
        print("\nContinuing conversation.")
    else:
        print("\nStarting a new conversation.")

    print("Type 'lets exit' to leave.\n")

    while True:
        message = input("You: ").strip()

        if message.lower() == "lets exit":
            print("\nGoodbye.")
            break

        if not message:
            continue

        if conversation_id:
            payload = {
                "action": "continue",
                "username": username,
                "conversation_id": conversation_id,
                "message": message,
            }
        else:
            payload = {
                "action": "new",
                "username": username,
                "message": message,
            }

        try:
            result = send_to_saha(payload)

            if not result.get("success", True):
                print("\nSAHA error:", result)
                continue

            if not conversation_id:
                conversation_id = result.get("conversation_id")

            print("\nSAHA:", result.get("response", result))

        except requests.RequestException as exc:
            print("\nConnection error:", exc)


if __name__ == "__main__":
    main()

