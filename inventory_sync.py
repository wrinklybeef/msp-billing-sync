"""Join N-able client inventory to an M365 backup billing export."""

import argparse
import csv
import os
from pathlib import Path
import xml.etree.ElementTree as ET

HEADERS = ["Client ID", "Client Name", "Servers", "Workstations", "M365 Billable Users"]
API_URL = "https://www.systemmonitor.us/api/?apikey=YOUR_API_KEY&service=list_clients"

def read_inventory(xml_text, excluded=()):
    clients = []
    seen = set()
    excluded = {value.strip().casefold() for value in excluded}

    for client in ET.fromstring(xml_text).findall(".//client"):
        client_id = (client.findtext("clientid") or "").strip()
        if not client_id:
            raise ValueError("Inventory contains a client without an ID")
        key = client_id.casefold()
        if key in excluded:
            continue
        if key in seen:
            raise ValueError(f"Duplicate inventory client ID: {client_id}")
        seen.add(key)
        clients.append((client_id, (client.findtext("name") or "").strip(),
                        parse_count(client.findtext("server_count"), "server", client_id),
                        parse_count(client.findtext("workstation_count"), "workstation", client_id)))
    return clients


def parse_count(value, kind, client_id):
    try:
        count = int(value)
        if count < 0:
            raise ValueError()
        return count
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {kind} count for client {client_id}") from None


def read_billing(csv_path):
    result = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"Partner reference", "Total M365 billable users"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Billing CSV is missing required columns")
        for row in reader:
            key = (row["Partner reference"] or "").strip().casefold()
            raw = (row["Total M365 billable users"] or "").strip()
            if not key:
                continue
            if key in result:
                raise ValueError(f"Duplicate billing partner reference: {key}")
            result[key] = parse_count(raw, "M365 billable user", key) if raw else ""
    return result


def merge(inventory, billing):
    rows = [HEADERS]
    ids = set()
    for client_id, name, servers, workstations in inventory:
        ids.add(client_id.casefold())
        rows.append([client_id, name, servers, workstations,
                     billing.get(client_id.casefold(), "")])
    unmatched = sorted(set(billing) - ids)
    return rows, unmatched


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def publish_to_sheets(rows, spreadsheet_id, worksheet_name, credentials_file):
    import gspread

    sheet = gspread.service_account(filename=credentials_file).open_by_key(spreadsheet_id)
    worksheet = sheet.worksheet(worksheet_name)
    previous = len(worksheet.get_all_values())

    # Update first, then remove obsolete rows so a failed write does not blank the sheet.
    worksheet.update(range_name="A1", values=rows, value_input_option="RAW")
    if previous > len(rows):
        worksheet.batch_clear([f"A{len(rows) + 1}:E{previous}"])


def load_inventory(path, use_live):
    if not use_live:
        return Path(path).read_text(encoding="utf-8")

    import requests

    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()
    return response.text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default="samples/clients.xml", help="N-able XML export")
    parser.add_argument("--billing", default="samples/m365_billing.csv", help="Cove billing CSV")
    parser.add_argument("--output", default="output/client_inventory.csv")
    parser.add_argument("--exclude", action="append", default=[], help="Client ID to omit; repeat as needed")
    parser.add_argument("--live", action="store_true", help="Fetch XML from NABLE_CLIENTS_URL")
    parser.add_argument("--publish", action="store_true", help="Update a Google Sheets worksheet")
    args = parser.parse_args()

    inventory = read_inventory(load_inventory(args.inventory, args.live), args.exclude)
    billing = read_billing(args.billing)
    rows, unmatched = merge(inventory, billing)
    write_csv(args.output, rows)

    print(f"Wrote {len(rows) - 1} clients to {args.output}")
    if unmatched:
        print(f"Billing references without a matching client: {len(unmatched)} ({', '.join(unmatched)})")

    if args.publish:
        required = ("GOOGLE_SHEET_ID", "GOOGLE_WORKSHEET", "GOOGLE_CREDENTIALS_FILE")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            parser.error("Missing environment settings: " + ", ".join(missing))
        publish_to_sheets(rows, *(os.environ[name] for name in required))
        print("Updated Google Sheets worksheet")


if __name__ == "__main__":
    main()
