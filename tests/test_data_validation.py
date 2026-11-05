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


if __name__ == "__main__":
    unittest.main()
