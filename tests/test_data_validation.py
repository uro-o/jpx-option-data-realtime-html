import unittest

import get_option_data


class ContractSnapshotValidationTests(unittest.TestCase):
    def setUp(self):
        self.contracts = ["2026-11", "2026-12", "2027-03"]

    def make_records(self, contracts=None):
        contracts = contracts or self.contracts
        rows = []
        for contract in contracts:
            rows.extend([
                {
                    "contract": contract,
                    "option_type": "CALL",
                    "strike": 70000,
                },
                {
                    "contract": contract,
                    "option_type": "PUT",
                    "strike": 70000,
                },
            ])
        return rows

    def test_accepts_three_complete_contracts(self):
        get_option_data.validate_contract_records(
            self.make_records(),
            self.contracts,
        )

    def test_rejects_missing_contract(self):
        rows = self.make_records(self.contracts[:2])
        with self.assertRaisesRegex(RuntimeError, "no records"):
            get_option_data.validate_contract_records(
                rows,
                self.contracts,
            )

    def test_rejects_missing_call_or_put_pair(self):
        rows = self.make_records()
        rows.remove(next(
            row for row in rows
            if row["contract"] == "2026-11"
            and row["option_type"] == "PUT"
        ))
        with self.assertRaisesRegex(RuntimeError, "missing"):
            get_option_data.validate_contract_records(
                rows,
                self.contracts,
            )

    def test_rejects_duplicate_strike_record(self):
        rows = self.make_records()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            get_option_data.validate_contract_records(
                rows,
                self.contracts,
            )

    def test_rejects_unexpected_contract(self):
        rows = self.make_records()
        rows.append({
            "contract": "2027-06",
            "option_type": "CALL",
            "strike": 70000,
        })
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            get_option_data.validate_contract_records(
                rows,
                self.contracts,
            )


    def test_number_preserves_zero_and_missing_values(self):
        self.assertEqual(get_option_data.number("0"), 0.0)
        self.assertEqual(get_option_data.number("1,250"), 1250.0)
        self.assertIsNone(get_option_data.number(""))
        self.assertIsNone(get_option_data.number(None))
        self.assertIsNone(get_option_data.number("-"))
        self.assertIsNone(get_option_data.number("not-a-number"))

    def test_difference_is_not_computed_when_either_value_is_missing(self):
        previous = [{
            "contract": "2026-11",
            "option_type": "CALL",
            "strike": "70000",
            "open_interest": "",
            "volume": "10",
            "last_price": "",
            "ask_quantity": "",
            "bid_quantity": "",
        }]
        current = [{
            "contract": "2026-11",
            "option_type": "CALL",
            "strike": "70000",
            "open_interest": "500",
            "volume": "120",
            "last_price": "",
            "ask_quantity": "",
            "bid_quantity": "",
        }]

        result = get_option_data.calculate_differences(
            previous,
            current,
        )[0]

        self.assertIsNone(result["open_interest_diff"])
        self.assertEqual(result["volume_diff"], 110.0)
        self.assertIsNone(result["last_price_diff"])
        self.assertEqual(result["alert_type"], "VOLUME")


if __name__ == "__main__":
    unittest.main()
