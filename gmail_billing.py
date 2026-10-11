"""Extract a Cove M365 billing table from a Gmail message into a CSV."""

import argparse
import base64
import csv
import os
from pathlib import Path
import tempfile

HEADERS = ["Partner reference", "Total M365 billable users"]
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def extract_billing(html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        records = []
        indices = None
        seen = set()
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"], recursive=False)]
            labels = [" ".join(cell.casefold().split()) for cell in cells]
            if indices is None:
                partner = next((i for i, value in enumerate(labels) if value == "partner reference"), None)
                count = next((i for i, value in enumerate(labels) if "m365" in value and "billable" in value), None)
                if partner is not None and count is not None:
                    indices = partner, count
                continue
            if len(cells) <= max(indices):
                continue
            client_id, total = (cells[index].strip() for index in indices)
            if not client_id:
                continue
            key = client_id.casefold()
            if key in seen:
                raise ValueError(f"Duplicate billing partner reference: {client_id}")
            if total and (not total.isdecimal() or int(total) < 0):
                raise ValueError(f"Invalid M365 billing count for partner reference: {client_id}")
            seen.add(key)
            records.append([client_id, total])
        if indices is not None:
            if not records:
                raise ValueError("Billing table has no client rows")
            return records
    raise ValueError("No billing table found with Partner Reference and M365 Billable Users columns")


def message_html(payload):
    mime_type = payload.get("mimeType")
    encoded = payload.get("body", {}).get("data")
    if encoded and mime_type in ("text/html", None):
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        return decoded.decode("utf-8")
    for part in payload.get("parts", []):
        html = message_html(part)
        if html is not None:
            return html
    return None


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_file = Path(os.environ.get("GMAIL_TOKEN_FILE", "config/gmail_token.json"))
    client_file = Path(os.environ.get("GMAIL_OAUTH_CLIENT_FILE", "config/gmail_credentials.json"))
    credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES) if token_file.exists() else None
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not client_file.is_file():
                raise FileNotFoundError(f"Gmail OAuth client file not found: {client_file}")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
            credentials = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def latest_billing_html(service, query):
    result = service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    messages = result.get("messages", [])
    if not messages:
        raise ValueError("No Gmail message matches the configured billing report query")
    message = service.users().messages().get(userId="me", id=messages[0]["id"], format="full").execute()
    html = message_html(message.get("payload", {}))
    if html is None:
        raise ValueError("Matching Gmail message contains no HTML report")
    return html


def save_csv(path, records):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=destination.parent,
                                         prefix=".billing-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.writer(handle)
            writer.writerow(HEADERS)
            writer.writerows(records)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", help="Read a saved HTML report instead of using Gmail (for testing)")
    parser.add_argument("--output", default="output/m365_billing.csv")
    args = parser.parse_args()

    if args.html:
        html = Path(args.html).read_text(encoding="utf-8")
    else:
        query = os.environ.get("GMAIL_SEARCH_QUERY", "").strip()
        if not query:
            parser.error("Set GMAIL_SEARCH_QUERY to identify the Cove billing email")
        html = latest_billing_html(gmail_service(), query)

    records = extract_billing(html)
    save_csv(args.output, records)
    print(f"Saved {len(records)} billing rows to {args.output}")


if __name__ == "__main__":
    main()
