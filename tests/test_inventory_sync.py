import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from inventory_sync import HEADERS, merge, parse_count, publish_to_sheets, read_billing, read_inventory


class InventorySyncTests(unittest.TestCase):
    def test_join_and_missing_backup_count(self):
        xml = '<clients><client><clientid> AbC </clientid><name>Example</name><server_count>2</server_count><workstation_count>5</workstation_count></client><client><clientid>def</clientid><server_count>0</server_count><workstation_count>3</workstation_count></client></clients>'
        rows, unmatched = merge(read_inventory(xml), {'abc': 6, 'orphan': 2})
        self.assertEqual(rows, [HEADERS, ['AbC', 'Example', 2, 5, 6], ['def', '', 0, 3, '']])
        self.assertEqual(unmatched, ['orphan'])

    def test_excluded_client(self):
        xml = '<clients><client><clientid>123</clientid><server_count>2</server_count><workstation_count>1</workstation_count></client></clients>'
        self.assertEqual(read_inventory(xml, ['123']), [])

    def test_duplicate_inventory_ids_rejected(self):
        xml = '<clients><client><clientid>A</clientid><server_count>1</server_count><workstation_count>1</workstation_count></client><client><clientid>a</clientid><server_count>1</server_count><workstation_count>1</workstation_count></client></clients>'
        with self.assertRaisesRegex(ValueError, 'Duplicate inventory'):
            read_inventory(xml)

    def test_invalid_count_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Invalid server count'):
            parse_count('-1', 'server', '123')

    def test_billing_headers_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'billing.csv'
            path.write_text('Partner reference,Total M365 billable users\n ABC ,9\n', encoding='utf-8')
            self.assertEqual(read_billing(path), {'abc': 9})
            path.write_text('Partner reference,Total M365 billable users\nABC,9\nabc,10\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Duplicate billing'):
                read_billing(path)

    def test_sheet_write_overwrites_and_clears_stale_rows(self):
        ws = Mock()
        ws.get_all_values.return_value = [['old']] * 6
        gspread = Mock()
        gspread.service_account.return_value.open_by_key.return_value.worksheet.return_value = ws
        with patch.dict('sys.modules', {'gspread': gspread}):
            publish_to_sheets([HEADERS, ['x', 'Test', 1, 2, 3]], 'fake-sheet', 'Inventory', 'placeholder.json')
        ws.update.assert_called_once_with(range_name='A1', values=[HEADERS, ['x', 'Test', 1, 2, 3]], value_input_option='RAW')
        ws.batch_clear.assert_called_once_with(['A3:E6'])

    def test_failed_sheet_update_does_not_clear(self):
        ws = Mock()
        ws.get_all_values.return_value = [['old']] * 6
        ws.update.side_effect = RuntimeError('failed')
        gspread = Mock()
        gspread.service_account.return_value.open_by_key.return_value.worksheet.return_value = ws
        with patch.dict('sys.modules', {'gspread': gspread}):
            with self.assertRaises(RuntimeError):
                publish_to_sheets([HEADERS], 'fake-sheet', 'Inventory', 'placeholder.json')
        ws.batch_clear.assert_not_called()


if __name__ == '__main__':
    unittest.main()
