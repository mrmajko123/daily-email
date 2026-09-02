import os
import json
import smtplib
import imaplib
from email.mime.text import MIMEText
from datetime import date
from urllib.request import urlopen, Request

# ---- Settings pulled from environment variables (set as GitHub Secrets) ----
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"]      # app password, not your normal password
RECEIVER_EMAIL = os.environ["RECEIVER_EMAIL"]
MESSAGE_TEXT = os.environ.get("MESSAGE_TEXT", "")
START_DATE = os.environ["START_DATE"]                # format: YYYY-MM-DD
NTFY_TOPIC = os.environ["NTFY_TOPIC"]                # your private ntfy.sh topic name

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))

STATE_FILE = "state.json"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"stopped": False}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_day_count(start_date_str: str) -> int:
    start = date.fromisoformat(start_date_str)
    today = date.today()
    return (today - start).days + 1


def build_message(day_count: int) -> MIMEText:
    body = f"{MESSAGE_TEXT}\n\nDay {day_count}"
    msg = MIMEText(body)
    msg["Subject"] = f"Day {day_count}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    return msg


def send_email(msg: MIMEText) -> None:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, [RECEIVER_EMAIL], msg.as_string())


def check_for_reply() -> bool:
    """Returns True if the recipient has sent a new (unseen) email in the inbox."""
    with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as imap:
        imap.login(SENDER_EMAIL, SENDER_PASSWORD)
        imap.select("INBOX")
        status, data = imap.search(None, f'(UNSEEN FROM "{RECEIVER_EMAIL}")')
        if status != "OK":
            return False
        ids = data[0].split()
        if ids:
            for msg_id in ids:
                imap.store(msg_id, "+FLAGS", "\\Seen")
            return True
        return False


def push_notify(title: str, message: str) -> None:
    req = Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title},
        method="POST",
    )
    urlopen(req, timeout=10)


if __name__ == "__main__":
    state = load_state()

    if state.get("stopped"):
        print("Recipient already replied previously. Not sending, not checking again.")
    else:
        replied = check_for_reply()
        if replied:
            state["stopped"] = True
            save_state(state)
            push_notify(
                "Reply received!",
                f"{RECEIVER_EMAIL} replied. Daily emails have been stopped.",
            )
            print("Reply detected. Notification sent. Future emails stopped.")
        else:
            count = get_day_count(START_DATE)
            message = build_message(count)
            send_email(message)
            print(f"Sent day {count} email to {RECEIVER_EMAIL}")
