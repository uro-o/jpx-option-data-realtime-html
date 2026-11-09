import json
import pathlib
import shutil
import subprocess
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


    def test_oi_cell_distinguishes_dash_blank_zero_and_numeric(self):
        cases = [
            ("-", (0.0, "dash")),
            ("—", (0.0, "dash")),
            ("", (None, "blank")),
            ("0", (0.0, "numeric")),
            ("1,250", (1250.0, "numeric")),
            ("N/A", (None, "invalid")),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                cell = get_option_data.BeautifulSoup(
                    f"<td>{raw}</td>", "html.parser"
                ).td
                self.assertEqual(get_option_data.parse_oi_cell(cell), expected)

    def test_number_preserves_zero_and_missing_values(self):
        self.assertEqual(get_option_data.number("0"), 0.0)
        self.assertEqual(get_option_data.number("1,250"), 1250.0)
        self.assertIsNone(get_option_data.number(""))
        self.assertIsNone(get_option_data.number(None))
        self.assertIsNone(get_option_data.number("-"))
        self.assertIsNone(get_option_data.number("not-a-number"))
        self.assertIsNone(get_option_data.number("NaN"))
        self.assertIsNone(get_option_data.number("Infinity"))

    def test_difference_is_not_computed_when_either_value_is_missing(self):
        previous = [{
            "contract": "2026-11",
            "option_type": "CALL",
            "strike": "70000",
            "trading_day": "2026/11/05",
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
            "trading_day": "2026/11/05",
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


    def test_discord_message_handles_missing_metrics(self):
        message = get_option_data.build_discord_message({
            "contract": "2026-11",
            "option_type": "CALL",
            "strike": 70000,
            "open_interest_diff": None,
            "volume_diff": 120,
            "last_price_diff": None,
            "current_open_interest": None,
            "current_volume": 120,
            "current_last_price": None,
            "alert_type": "VOLUME",
        })
        self.assertIn("取得不可", message)
        self.assertIn("—", message)


    def test_volume_difference_is_suppressed_across_trading_days(self):
        previous = [{
            "contract": "2026-11",
            "option_type": "CALL",
            "strike": "70000",
            "trading_day": "2026/11/05",
            "open_interest": "100",
            "volume": "500",
            "last_price": "1000",
            "ask_quantity": "10",
            "bid_quantity": "10",
        }]
        current = [{
            "contract": "2026-11",
            "option_type": "CALL",
            "strike": "70000",
            "trading_day": "2026/11/06",
            "open_interest": "100",
            "volume": "20",
            "last_price": "1000",
            "ask_quantity": "10",
            "bid_quantity": "10",
        }]

        result = get_option_data.calculate_differences(
            previous,
            current,
        )[0]

        self.assertIsNone(result["volume_diff"])
        self.assertEqual(result["open_interest_diff"], 0.0)
        self.assertEqual(result["alert_type"], "")


class DashboardDataQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("Node.js is required for dashboard JavaScript tests")
        html_path = pathlib.Path(__file__).resolve().parents[1] / "docs" / "index.html"
        html = html_path.read_text(encoding="utf-8")

        def extract(start, end):
            a = html.index(start)
            b = html.index(end, a)
            return html[a:b]

        cls.build_strike_map_js = extract(
            "function buildStrikeMap(){",
            "function calculateMaxPain(",
        )
        cls.oi_complete_js = extract(
            "function areOIValuesComplete(",
            "function hasAnyOI(",
        )
        cls.has_any_oi_js = extract(
            "function hasAnyOI(",
            "function loadData(",
        )
        cls.calculate_max_pain_js = extract(
            "function calculateMaxPain(",
            "function setMaxPainDisplay(",
        )

    def evaluate_dashboard_quality(self, rows):
        script = f"""
const allData = {json.dumps(rows)};
const selectedContract = "2026-11";
function isExpiredContract() {{ return false; }}
function num(value) {{
  if (value === null || value === undefined) return null;
  const text = String(value).replace(/,/g, "").trim();
  if (text === "" || ["-", "--", "－", "―", "—"].includes(text)) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}}
{self.build_strike_map_js}
{self.oi_complete_js}
{self.has_any_oi_js}
{self.calculate_max_pain_js}
const snapshot = buildStrikeMap();
const maxPain = calculateMaxPain(snapshot.rows, snapshot.quality);
console.log(JSON.stringify({{
  quality: snapshot.quality,
  oiComplete: areOIValuesComplete(snapshot.rows, snapshot.quality),
  maxPain
}}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_dashboard_keeps_available_strike_oi_visible_when_incomplete(self):
        html_path = pathlib.Path(__file__).resolve().parents[1] / "docs" / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("const callOILabel=formatNumber(r.callOI);", html)
        self.assertIn("const putOILabel=formatNumber(r.putOI);", html)
        self.assertNotIn('const callOILabel=oiComplete?formatNumber(r.callOI):"—";', html)
        self.assertIn("CALL OI ${quality.strikeCount-quality.missingCallOIValues}", html)
        self.assertIn("PUT OI ${quality.strikeCount-quality.missingPutOIValues}", html)
        self.assertIn("QRI「-」は0として集計（原表状態保持）", html)

    def base_pair(self):
        return [
            {"contract": "2026-11", "option_type": "CALL", "strike": "70000", "open_interest": "10"},
            {"contract": "2026-11", "option_type": "PUT", "strike": "70000", "open_interest": "20"},
            {"contract": "2026-11", "option_type": "CALL", "strike": "70250", "open_interest": "30"},
            {"contract": "2026-11", "option_type": "PUT", "strike": "70250", "open_interest": "40"},
        ]

    def test_dashboard_accepts_complete_pairs_and_zero_oi(self):
        rows = self.base_pair()
        rows[0]["open_interest"] = "0"
        result = self.evaluate_dashboard_quality(rows)
        self.assertTrue(result["quality"]["pairComplete"])
        self.assertTrue(result["oiComplete"])
        self.assertIsNotNone(result["maxPain"])

    def test_dashboard_rejects_missing_call_put_counterpart(self):
        rows = self.base_pair()
        rows.pop(1)
        result = self.evaluate_dashboard_quality(rows)
        self.assertFalse(result["quality"]["pairComplete"])
        self.assertEqual(result["quality"]["missingPutStrikes"], 1)
        self.assertFalse(result["oiComplete"])
        self.assertIsNone(result["maxPain"])

    def test_dashboard_rejects_duplicate_side_rows(self):
        rows = self.base_pair()
        rows.append(dict(rows[0]))
        result = self.evaluate_dashboard_quality(rows)
        self.assertEqual(result["quality"]["duplicateRows"], 1)
        self.assertFalse(result["quality"]["pairComplete"])
        self.assertFalse(result["oiComplete"])
        self.assertIsNone(result["maxPain"])

    def test_dashboard_rejects_incomplete_oi_but_reports_coverage(self):
        rows = self.base_pair()
        rows[0]["open_interest"] = ""
        result = self.evaluate_dashboard_quality(rows)
        self.assertTrue(result["quality"]["pairComplete"])
        self.assertEqual(result["quality"]["missingOIValues"], 1)
        self.assertEqual(result["quality"]["missingCallOIValues"], 1)
        self.assertEqual(result["quality"]["missingPutOIValues"], 0)
        self.assertEqual(result["quality"]["oiRate"], 75.0)
        self.assertFalse(result["oiComplete"])
        self.assertIsNone(result["maxPain"])

    def test_dashboard_counts_qri_dash_states_without_treating_them_as_zero(self):
        rows = self.base_pair()
        rows[0]["open_interest"] = ""
        rows[0]["open_interest_status"] = "dash"
        rows[1]["open_interest_status"] = "numeric"
        result = self.evaluate_dashboard_quality(rows)
        self.assertTrue(result["quality"]["oiStatusAvailable"])
        self.assertEqual(result["quality"]["callOIdash"], 1)
        self.assertEqual(result["quality"]["putOIdash"], 0)
        self.assertFalse(result["oiComplete"])
        self.assertIsNone(result["maxPain"])

    def test_dashboard_rejects_invalid_rows(self):
        rows = self.base_pair()
        rows.append({
            "contract": "2026-11",
            "option_type": "OTHER",
            "strike": "70500",
            "open_interest": "100",
        })
        result = self.evaluate_dashboard_quality(rows)
        self.assertEqual(result["quality"]["invalidRows"], 1)
        self.assertFalse(result["oiComplete"])
        self.assertIsNone(result["maxPain"])


if __name__ == "__main__":
    unittest.main()
