import base64
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from gmail_billing import extract_billing, latest_billing_html, message_html, save_csv


EXAMPLE = Path(__file__).resolve().parent.parent / "samples" / "cove_email.html"


class GmailBillingTests(unittest.TestCase):
    def test_extracts_billing_table(self):
        rows = extract_billing(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(rows[0], ["10001", "24"])
        self.assertEqual(rows[-1], ["19999", "6"])
        self.assertEqual(len(rows), 4)

    def test_rejects_wrong_report(self):
        with self.assertRaisesRegex(ValueError, "No billing table"):
            extract_billing("<html><table><tr><td>Unrelated</td></tr></table></html>")

    def test_rejects_duplicate_references(self):
        html = "<table><tr><th>Partner Reference</th><th>M365 Billable Users</th></tr>" \
               "<tr><td>AB</td><td>4</td></tr><tr><td>ab</td><td>5</td></tr></table>"
        with self.assertRaisesRegex(ValueError, "Duplicate billing"):
            extract_billing(html)

    def test_rejects_nonnumeric_counts(self):
        html = "<table><tr><th>Partner Reference</th><th>M365 Billable Users</th></tr>" \
               "<tr><td>AB</td><td>unknown</td></tr></table>"
        with self.assertRaisesRegex(ValueError, "Invalid M365"):
            extract_billing(html)

    def test_reads_nested_html_message(self):
        encoded = base64.urlsafe_b64encode(b"<table>example</table>").decode("ascii")
        payload = {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": "abc"}},
            {"mimeType": "text/html", "body": {"data": encoded.rstrip("=")}}
        ]}
        self.assertEqual(message_html(payload), "<table>example</table>")

    def test_gmail_query_fetches_matching_message(self):
        service = Mock()
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "fake-id"}]}
        service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "payload": {"mimeType": "text/html", "body": {
                "data": base64.urlsafe_b64encode(b"<table>ok</table>").decode("ascii")}}}
        self.assertEqual(latest_billing_html(service, "subject:report"), "<table>ok</table>")
        service.users.return_value.messages.return_value.list.assert_called_once_with(
            userId="me", q="subject:report", maxResults=1)

    def test_no_match_errors_instead_of_using_old_csv(self):
        service = Mock()
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {}
        with self.assertRaisesRegex(ValueError, "No Gmail message"):
            latest_billing_html(service, "subject:report")

    def test_save_csv_replaces_previous_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "billing.csv"
            path.write_text("old data", encoding="utf-8")
            save_csv(path, [["10001", "24"]])
            with path.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(list(csv.reader(handle)), [
                    ["Partner reference", "Total M365 billable users"], ["10001", "24"]])


if __name__ == "__main__":
    unittest.main()
