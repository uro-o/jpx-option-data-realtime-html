import csv
import json
import os
import re
from pathlib import Path

import requests


# ============================================================
# Configuration
# ============================================================

DIFFERENCE_FILE = Path("data/differences.csv")
NOTIFIED_FILE = Path("data/notified_alerts.csv")

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL"
)


# ============================================================
# Large trade thresholds
# ============================================================

VOLUME_THRESHOLD = 500

OI_THRESHOLD = 300

OI_VOLUME_COMBINED_OI = 100
OI_VOLUME_COMBINED_VOLUME = 100

TRADE_VALUE_THRESHOLD = 100_000_000

PRICE_CHANGE_THRESHOLD = 500


# Nikkei 225 option multiplier
# 1 point = 100 yen
OPTION_MULTIPLIER = 100


# ============================================================
# Helpers
# ============================================================

def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def to_number(value):

    if value is None:
        return None

    value = clean(value)

    if not value:
        return None

    if value in (
        "-",
        "--",
        "－",
        "―",
    ):
        return None

    value = value.replace(",", "")
    value = value.replace("%", "")

    # Remove plus sign
    value = value.replace("+", "")

    try:

        number = float(value)

        if number.is_integer():
            return int(number)

        return number

    except ValueError:

        return None


def format_number(value):

    if value is None:
        return "-"

    try:

        return f"{float(value):,.0f}"

    except Exception:

        return str(value)


def format_yen(value):

    if value is None:
        return "-"

    try:

        return f"{float(value):,.0f}円"

    except Exception:

        return str(value)


# ============================================================
# Read CSV
# ============================================================

def load_differences():

    if not DIFFERENCE_FILE.exists():

        print(
            f"[INFO] "
            f"{DIFFERENCE_FILE} "
            f"does not exist."
        )

        return []

    with open(
        DIFFERENCE_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        rows = list(reader)

    print(
        f"[INFO] "
        f"Loaded {len(rows)} rows "
        f"from {DIFFERENCE_FILE}"
    )

    return rows


# ============================================================
# Find value from multiple possible column names
# ============================================================

def get_value(
    row,
    names,
):

    for name in names:

        if name in row:

            value = row.get(name)

            if value not in (
                None,
                "",
            ):

                return value

    return None


# ============================================================
# Detect large option activity
# ============================================================

def analyze_row(row):

    # --------------------------------------------------------
    # Basic information
    # --------------------------------------------------------

    contract = get_value(
        row,
        [
            "contract",
            "Contract",
        ],
    )

    option_type = get_value(
        row,
        [
            "option_type",
            "Option Type",
            "type",
        ],
    )

    strike = get_value(
        row,
        [
            "strike",
            "Strike",
        ],
    )

    qri_update_time = get_value(
        row,
        [
            "qri_update_time",
            "QRI update time",
            "update_time",
        ],
    )

    collected_at = get_value(
        row,
        [
            "collected_at",
            "collected",
        ],
    )

    # --------------------------------------------------------
    # Difference values
    # --------------------------------------------------------

    volume_diff = to_number(
        get_value(
            row,
            [
                "volume_diff",
                "volume_change",
                "diff_volume",
                "volume_delta",
                "volume_difference",
            ],
        )
    )

    oi_diff = to_number(
        get_value(
            row,
            [
                "open_interest_diff",
                "oi_diff",
                "open_interest_change",
                "oi_change",
                "diff_open_interest",
                "open_interest_delta",
            ],
        )
    )

    last_price_diff = to_number(
        get_value(
            row,
            [
                "last_price_diff",
                "price_diff",
                "last_price_change",
                "price_change",
                "diff_last_price",
            ],
        )
    )

    # --------------------------------------------------------
    # Current values
    # --------------------------------------------------------

    volume = to_number(
        get_value(
            row,
            [
                "volume",
                "current_volume",
            ],
        )
    )

    open_interest = to_number(
        get_value(
            row,
            [
                "open_interest",
                "oi",
                "current_open_interest",
            ],
        )
    )

    last_price = to_number(
        get_value(
            row,
            [
                "last_price",
                "price",
                "current_price",
            ],
        )
    )

    # --------------------------------------------------------
    # Estimate trade value
    #
    # volume difference × option price × 100
    # --------------------------------------------------------

    trade_value = None

    if (
        volume_diff is not None
        and last_price is not None
        and volume_diff > 0
        and last_price > 0
    ):

        trade_value = (
            volume_diff
            * last_price
            * OPTION_MULTIPLIER
        )

    # ========================================================
    # Detection
    # ========================================================

    reasons = []

    # --------------------------------------------------------
    # 1. Large volume increase
    # --------------------------------------------------------

    if (
        volume_diff is not None
        and volume_diff >= VOLUME_THRESHOLD
    ):

        reasons.append(
            f"📈 出来高 +{format_number(volume_diff)}枚"
        )

    # --------------------------------------------------------
    # 2. Large OI increase
    # --------------------------------------------------------

    if (
        oi_diff is not None
        and oi_diff >= OI_THRESHOLD
    ):

        reasons.append(
            f"📊 建玉 +{format_number(oi_diff)}枚"
        )

    # --------------------------------------------------------
    # 3. Large estimated trade value
    # --------------------------------------------------------

    if (
        trade_value is not None
        and trade_value >= TRADE_VALUE_THRESHOLD
    ):

        reasons.append(
            f"💰 推定売買代金 {format_yen(trade_value)}"
        )

    # --------------------------------------------------------
    # 4. OI + Volume simultaneous increase
    # --------------------------------------------------------

    if (
        oi_diff is not None
        and volume_diff is not None
        and oi_diff >= OI_VOLUME_COMBINED_OI
        and volume_diff >= OI_VOLUME_COMBINED_VOLUME
    ):

        reasons.append(
            "🔥 OI増加＋出来高急増"
        )

    # --------------------------------------------------------
    # 5. Large option price movement
    # --------------------------------------------------------

    if (
        last_price_diff is not None
        and abs(last_price_diff)
        >= PRICE_CHANGE_THRESHOLD
    ):

        if last_price_diff > 0:

            reasons.append(
                f"🚀 現在値 +{format_number(last_price_diff)}円"
            )

        else:

            reasons.append(
                f"🔻 現在値 {format_number(last_price_diff)}円"
            )

    # --------------------------------------------------------
    # No alert
    # --------------------------------------------------------

    if not reasons:

        return None

    # ========================================================
    # Alert object
    # ========================================================

    return {

        "contract":
            contract or "-",

        "option_type":
            option_type or "-",

        "strike":
            strike or "-",

        "qri_update_time":
            qri_update_time or "-",

        "collected_at":
            collected_at or "-",

        "volume_diff":
            volume_diff,

        "oi_diff":
            oi_diff,

        "last_price_diff":
            last_price_diff,

        "volume":
            volume,

        "open_interest":
            open_interest,

        "last_price":
            last_price,

        "trade_value":
            trade_value,

        "reasons":
            reasons,
    }


# ============================================================
# Notification key
#
# Prevent duplicate Discord notifications
# ============================================================

def make_alert_key(alert):

    return "|".join(
        [
            clean(alert["contract"]),
            clean(alert["option_type"]),
            clean(alert["strike"]),
            clean(alert["qri_update_time"]),
        ]
    )


# ============================================================
# Load notified alerts
# ============================================================

def load_notified():

    if not NOTIFIED_FILE.exists():

        return set()

    notified = set()

    try:

        with open(
            NOTIFIED_FILE,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                key = row.get(
                    "alert_key"
                )

                if key:

                    notified.add(key)

    except Exception as e:

        print(
            f"[WARNING] "
            f"Could not load notified alerts: "
            f"{e}"
        )

    return notified


# ============================================================
# Save notification key
# ============================================================

def save_notified_key(
    key
):

    file_exists = (
        NOTIFIED_FILE.exists()
    )

    with open(
        NOTIFIED_FILE,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "alert_key"
            ],
        )

        if not file_exists:

            writer.writeheader()

        writer.writerow(
            {
                "alert_key": key
            }
        )


# ============================================================
# Discord message
# ============================================================

def create_message(
    alert
):

    option_type = (
        alert["option_type"]
    )

    if option_type == "CALL":

        emoji = "🟢"

    elif option_type == "PUT":

        emoji = "🔴"

    else:

        emoji = "⚪"

    lines = []

    lines.append(
        "🚨 **JPX OPTION LARGE ACTIVITY**"
    )

    lines.append(
        ""
    )

    lines.append(
        f"{emoji} **{option_type}**"
    )

    lines.append(
        f"限月: **{alert['contract']}**"
    )

    lines.append(
        f"Strike: **{alert['strike']}**"
    )

    lines.append(
        ""
    )

    lines.append(
        "**検知理由**"
    )

    for reason in alert["reasons"]:

        lines.append(
            f"• {reason}"
        )

    lines.append(
        ""
    )

    lines.append(
        "**現在データ**"
    )

    lines.append(
        f"出来高: {format_number(alert['volume'])}"
    )

    lines.append(
        f"出来高差分: {format_number(alert['volume_diff'])}"
    )

    lines.append(
        f"建玉: {format_number(alert['open_interest'])}"
    )

    lines.append(
        f"建玉差分: {format_number(alert['oi_diff'])}"
    )

    lines.append(
        f"現在値: {format_yen(alert['last_price'])}"
    )

    lines.append(
        f"価格差分: {format_yen(alert['last_price_diff'])}"
    )

    if alert["trade_value"] is not None:

        lines.append(
            f"推定売買代金: "
            f"{format_yen(alert['trade_value'])}"
        )

    lines.append(
        ""
    )

    lines.append(
        f"QRI更新: {alert['qri_update_time']}"
    )

    lines.append(
        f"取得時刻: {alert['collected_at']}"
    )

    return "\n".join(lines)


# ============================================================
# Send Discord
# ============================================================

def send_discord(
    message
):

    if not DISCORD_WEBHOOK_URL:

        raise RuntimeError(
            "DISCORD_WEBHOOK_URL "
            "is not configured."
        )

    payload = {

        "content":
            message,

        "username":
            "JPX Option Monitor",
    }

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json=payload,
        timeout=30,
    )

    print(
        f"[DISCORD] "
        f"status={response.status_code}"
    )

    response.raise_for_status()


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "========================================"
    )
    print(
        "JPX OPTION LARGE ACTIVITY DETECTOR"
    )
    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Check webhook
    # --------------------------------------------------------

    if not DISCORD_WEBHOOK_URL:

        print(
            "[ERROR] "
            "DISCORD_WEBHOOK_URL "
            "is not configured."
        )

        return

    # --------------------------------------------------------
    # Load differences
    # --------------------------------------------------------

    rows = load_differences()

    if not rows:

        print(
            "[INFO] "
            "No difference data."
        )

        return

    # --------------------------------------------------------
    # Load already notified
    # --------------------------------------------------------

    notified = load_notified()

    print(
        f"[INFO] "
        f"Already notified: "
        f"{len(notified)}"
    )

    # --------------------------------------------------------
    # Analyze
    # --------------------------------------------------------

    alerts = []

    for row in rows:

        alert = analyze_row(
            row
        )

        if alert is None:

            continue

        key = make_alert_key(
            alert
        )

        if key in notified:

            print(
                f"[SKIP] "
                f"Already notified: "
                f"{key}"
            )

            continue

        alerts.append(
            (
                key,
                alert,
            )
        )

    print(
        f"[ALERT] "
        f"New large activities: "
        f"{len(alerts)}"
    )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    for key, alert in alerts:

        message = create_message(
            alert
        )

        print()
        print(
            "----------------------------------------"
        )

        print(message)

        print(
            "----------------------------------------"
        )

        try:

            send_discord(
                message
            )

            save_notified_key(
                key
            )

            notified.add(
                key
            )

        except Exception as e:

            print(
                f"[ERROR] "
                f"Discord notification failed: "
                f"{e}"
            )

    print()
    print(
        "========================================"
    )

    print(
        "NOTIFICATION COMPLETE"
    )

    print(
        "========================================"


    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    main()
