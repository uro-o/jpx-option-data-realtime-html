import csv
import re
import calendar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import get_option_data as base


JST = timezone(timedelta(hours=9))

# Daily history is fixed to the end of the daytime session.
# The workflow may start a little later than the scheduled time, so
# we archive the first successful run at or after 15:45 JST.
FIXED_SNAPSHOT_HOUR = 15
FIXED_SNAPSHOT_MINUTE = 45


# ============================================================
# Contract calculation
# ============================================================

def second_friday(year, month):
    cal = calendar.monthcalendar(year, month)
    fridays = [
        week[calendar.FRIDAY]
        for week in cal
        if week[calendar.FRIDAY]
    ]
    return date(year, month, fridays[1])


def last_trading_day(year, month):
    # Nikkei 225 options normally end on the business day
    # immediately before the second Friday SQ day.
    d = second_friday(year, month) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def add_months(year, month, amount):
    index = year * 12 + (month - 1) + amount
    return index // 12, index % 12 + 1


def next_calendar_month(year, month):
    return add_months(year, month, 1)


def next_quarter_month(year, month):
    # Quarterly Nikkei 225 option months are Mar/Jun/Sep/Dec.
    quarters = (3, 6, 9, 12)
    for q in quarters:
        if q >= month:
            return year, q
    return year + 1, 3


def get_front_month(today):
    # Keep the current month until its final trading day.
    if today <= last_trading_day(today.year, today.month):
        return today.year, today.month
    return next_calendar_month(today.year, today.month)


def build_contracts(today):
    front_year, front_month = get_front_month(today)
    second_year, second_month = next_calendar_month(
        front_year,
        front_month,
    )

    # QRI's /2 page is the next quarterly contract in the
    # three-month set (e.g. Sep -> Dec, Oct -> Dec,
    # Nov -> Dec; after Dec SQ it becomes Mar).
    third_year, third_month = next_quarter_month(
        second_year,
        second_month,
    )

    contracts = {
        f"{front_year:04d}-{front_month:02d}":
            "https://svc.qri.jp/jpx/nkopm/",
        f"{second_year:04d}-{second_month:02d}":
            "https://svc.qri.jp/jpx/nkopm/1",
        f"{third_year:04d}-{third_month:02d}":
            "https://svc.qri.jp/jpx/nkopm/2",
    }

    return contracts


# ============================================================
# Fixed-time daily history
# ============================================================

def parse_trading_date(value):
    text = str(value or "").strip()

    patterns = (
        r"(\d{4})/(\d{2})/(\d{2})",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{4})\.(\d{2})\.(\d{2})",
    )

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return (
                f"{match.group(1)}-"
                f"{match.group(2)}-"
                f"{match.group(3)}"
            )

    return datetime.now(JST).strftime("%Y-%m-%d")


def snapshot_marker(trading_date):
    history_root = Path("data") / "history"
    history_root.mkdir(parents=True, exist_ok=True)
    return history_root / f".fixed-1545-{trading_date}.done"


def is_fixed_snapshot_time(now):
    target = now.replace(
        hour=FIXED_SNAPSHOT_HOUR,
        minute=FIXED_SNAPSHOT_MINUTE,
        second=0,
        microsecond=0,
    )
    return now >= target


def save_history_by_contract(records, trading_day=None):
    """
    Save exactly one daily history snapshot, beginning at 15:45 JST.

    The live data continues to update every 5 minutes. History is different:
    once the first successful run at/after 15:45 has been archived, later
    runs on the same day do not overwrite it.

    collected_at and qri_update_time remain in each CSV, so the actual
    acquisition/QRI time is visible even if GitHub Actions starts slightly
    after the target time.
    """
    if not records:
        return

    now = datetime.now(JST)

    if not is_fixed_snapshot_time(now):
        print(
            f"[HISTORY] Waiting for fixed snapshot time: "
            f"15:45 JST (current={now.strftime('%H:%M:%S')})"
        )
        return

    history_root = Path("data") / "history"
    history_root.mkdir(parents=True, exist_ok=True)

    # Prefer the trading date supplied by QRI.
    day_value = ""
    for record in records:
        day_value = record.get("trading_day") or ""
        if day_value:
            break

    date_string = parse_trading_date(
        day_value or trading_day
    )

    marker = snapshot_marker(date_string)

    if marker.exists():
        print(
            f"[HISTORY] Fixed 15:45 snapshot already saved: "
            f"{date_string}"
        )
        return

    grouped = {}
    for record in records:
        contract = str(record.get("contract") or "").strip()
        if not contract:
            continue
        grouped.setdefault(contract, []).append(record)

    if not grouped:
        print("[HISTORY] No contract records to archive.")
        return

    # Write every contract for the same trading day before creating the
    # marker. This prevents a partial snapshot from being treated as done.
    written_files = []

    for contract, contract_records in grouped.items():
        contract_dir = history_root / contract
        contract_dir.mkdir(parents=True, exist_ok=True)

        history_file = contract_dir / f"{date_string}.csv"

        with history_file.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=base.FIELDNAMES,
            )
            writer.writeheader()
            writer.writerows(contract_records)

        written_files.append(history_file)

        print(
            f"[HISTORY] Fixed 15:45 snapshot: {history_file} "
            f"records={len(contract_records)}"
        )

    marker.write_text(
        "fixed_snapshot=15:45 JST\n"
        f"archived_at={now.isoformat()}\n",
        encoding="utf-8",
    )

    print(
        f"[HISTORY] Snapshot completed: {date_string} "
        f"at/after 15:45 JST"
    )


# ============================================================
# Main
# ============================================================


def main():
    today = datetime.now(JST).date()
    contracts = build_contracts(today)

    print("========================================")
    print("DYNAMIC QRI CONTRACTS")
    print("========================================")
    print(f"Today (JST): {today}")
    print(
        f"Fixed history snapshot: "
        f"{FIXED_SNAPSHOT_HOUR:02d}:"
        f"{FIXED_SNAPSHOT_MINUTE:02d} JST"
    )

    for contract, url in contracts.items():
        print(f"{contract} -> {url}")

    # Replace the hard-coded month mapping in get_option_data.py.
    base.CONTRACTS = contracts

    # Replace the original mixed-contract daily history writer with
    # the fixed-time, per-contract daily snapshot writer.
    base.save_history = save_history_by_contract

    base.main()


if __name__ == "__main__":
    main()
