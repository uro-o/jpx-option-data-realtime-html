import csv
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests


# ============================================================
# Configuration
# ============================================================

DATA_DIR = Path("data")

DIFFERENCES_FILE = DATA_DIR / "differences.csv"
ALERTS_FILE = DATA_DIR / "alerts.csv"

JST = timezone(
    timedelta(hours=9)
)


# ============================================================
# Large trade thresholds
#
# ここを変更することで大口判定を調整できます
# ============================================================

# 出来高の増加量
VOLUME_THRESHOLD = 500

# OIの増加量
OI_INCREASE_THRESHOLD = 300

# OIの減少量
OI_DECREASE_THRESHOLD = 300


# ============================================================
# Discord
#
# GitHub Secrets に DISCORD_WEBHOOK_URL を登録します
# ============================================================

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL"
)


# ============================================================
# CSV helper
# ============================================================

def to_float(value):

    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    if value in ("-", "--", "None", "null"):
        return None

    value = value.replace(",", "")
    value = value.replace("%", "")

    try:
        return float(value)

    except ValueError:
        return None


# ============================================================
# Find column
# ============================================================

def find_column(
    fieldnames,
    candidates,
):

    if not fieldnames:
        return None

    normalized = {
        str(x).strip().lower(): x
        for x in fieldnames
    }

    for candidate in candidates:

        key = candidate.lower()

        if key in normalized:
            return normalized[key]

    return None


# ============================================================
# Load differences
# ============================================================

def load_differences():

    if not DIFFERENCES_FILE.exists():

        print(
            f"[ERROR] "
            f"{DIFFERENCES_FILE} "
            f"not found."
        )

        return []

    with open(
        DIFFERENCES_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        rows = list(reader)

        fieldnames = (
            reader.fieldnames or []
        )

    print(
        f"[DIFFERENCES] "
        f"records={len(rows)}"
    )

    print(
        f"[COLUMNS] "
        f"{fieldnames}"
    )

    return rows


# ============================================================
# Get value from row
# ============================================================

def get_value(
    row,
    fieldnames,
    candidates,
):

    column = find_column(
        fieldnames,
        candidates,
    )

    if column is None:
        return None

    return to_float(
        row.get(column)
    )


# ============================================================
# Get text value
# ============================================================

def get_text(
    row,
    fieldnames,
    candidates,
):

    column = find_column(
        fieldnames,
        candidates,
    )

    if column is None:
        return ""

    value = row.get(column)

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# Detect large trade
# ============================================================

def detect_alerts(rows):

    if not rows:
        return []

    fieldnames = list(rows[0].keys())

    alerts = []

    for row in rows:

        # ====================================================
        # Basic information
        # ====================================================

        contract = get_text(
            row,
            fieldnames,
            [
                "contract",
                "限月",
            ],
        )

        option_type = get_text(
            row,
            fieldnames,
            [
                "option_type",
                "option type",
                "type",
                "種類",
            ],
        )

        strike = get_text(
            row,
            fieldnames,
            [
                "strike",
                "権利行使価格",
            ],
        )

        qri_update_time = get_text(
            row,
            fieldnames,
            [
                "qri_update_time",
                "qri update time",
                "更新時刻",
            ],
        )

        collected_at = get_text(
            row,
            fieldnames,
            [
                "collected_at",
                "collected at",
                "取得時刻",
            ],
        )

        # ====================================================
        # Difference values
        # ====================================================

        volume_diff = get_value(
            row,
            fieldnames,
            [
                "volume_diff",
                "volume_difference",
                "volume_change",
                "volume_delta",
                "diff_volume",
                "取引高差分",
            ],
        )

        oi_diff = get_value(
            row,
            fieldnames,
            [
                "open_interest_diff",
                "open_interest_difference",
                "oi_diff",
                "oi_difference",
                "oi_change",
                "diff_open_interest",
                "建玉残差分",
            ],
        )

        last_price_diff = get_value(
            row,
            fieldnames,
            [
                "last_price_diff",
                "last_price_difference",
                "price_diff",
                "price_difference",
            ],
        )

        iv_diff = get_value(
            row,
            fieldnames,
            [
                "iv_diff",
                "iv_difference",
            ],
        )

        # ====================================================
        # Current values
        # ====================================================

        current_volume = get_value(
            row,
            fieldnames,
            [
                "volume",
                "current_volume",
                "取引高",
            ],
        )

        current_oi = get_value(
            row,
            fieldnames,
            [
                "open_interest",
                "current_open_interest",
                "oi",
                "建玉残",
            ],
        )

        current_price = get_value(
            row,
            fieldnames,
            [
                "last_price",
                "current_price",
                "現在値",
            ],
        )

        current_iv = get_value(
            row,
            fieldnames,
            [
                "iv",
                "current_iv",
            ],
        )

        # ====================================================
        # Detect conditions
        # ====================================================

        reasons = []

        score = 0

        # ----------------------------------------------------
        # Volume surge
        # ----------------------------------------------------

        if (
            volume_diff is not None
            and volume_diff >= VOLUME_THRESHOLD
        ):

            reasons.append(
                "取引高急増"
            )

            score += 2

        # ----------------------------------------------------
        # OI increase
        # ----------------------------------------------------

        if (
            oi_diff is not None
            and oi_diff >= OI_INCREASE_THRESHOLD
        ):

            reasons.append(
                "OI大幅増加"
            )

            score += 3

        # ----------------------------------------------------
        # OI decrease
        # ----------------------------------------------------

        if (
            oi_diff is not None
            and oi_diff <= -OI_DECREASE_THRESHOLD
        ):

            reasons.append(
                "OI大幅減少"
            )

            score += 2

        # ----------------------------------------------------
        # No alert
        # ----------------------------------------------------

        if not reasons:
            continue

        # ====================================================
        # Alert level
        # ====================================================

        if score >= 5:

            level = "🚨🚨🚨"

            level_name = (
                "VERY LARGE"
            )

        elif score >= 3:

            level = "🚨🚨"

            level_name = (
                "LARGE"
            )

        else:

            level = "🚨"

            level_name = (
                "LARGE CANDIDATE"
            )

        # ====================================================
        # CALL / PUT
        # ====================================================

        if option_type.upper() == "CALL":

            option_icon = "📈"

        elif option_type.upper() == "PUT":

            option_icon = "📉"

        else:

            option_icon = "📊"

        # ====================================================
        # Alert record
        # ====================================================

        alert = {

            "alert_time":
                datetime.now(
                    JST
                ).isoformat(
                    timespec="seconds"
                ),

            "level":
                level_name,

            "contract":
                contract,

            "option_type":
                option_type,

            "strike":
                strike,

            "qri_update_time":
                qri_update_time,

            "collected_at":
                collected_at,

            "volume_diff":
                volume_diff,

            "oi_diff":
                oi_diff,

            "current_volume":
                current_volume,

            "current_oi":
                current_oi,

            "current_price":
                current_price,

            "iv":
                current_iv,

            "last_price_diff":
                last_price_diff,

            "iv_diff":
                iv_diff,

            "reasons":
                " / ".join(
                    reasons
                ),
        }

        alert[
            "_score"
        ] = score

        alert[
            "_icon"
        ] = option_icon

        alert[
            "_level_icon"
        ] = level

        alerts.append(
            alert
        )

    return alerts


# ============================================================
# Save alerts.csv
# ============================================================

def save_alerts(
    alerts
):

    if not alerts:

        print(
            "[ALERT] "
            "No large trades detected."
        )

        return

    public_fields = [
        "alert_time",
        "level",
        "contract",
        "option_type",
        "strike",
        "qri_update_time",
        "collected_at",
        "volume_diff",
        "oi_diff",
        "current_volume",
        "current_oi",
        "current_price",
        "iv",
        "last_price_diff",
        "iv_diff",
        "reasons",
    ]

    file_exists = (
        ALERTS_FILE.exists()
    )

    with open(
        ALERTS_FILE,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=public_fields,
        )

        if not file_exists:

            writer.writeheader()

        for alert in alerts:

            writer.writerow({
                field:
                    alert.get(field)
                for field in public_fields
            })

    print(
        f"[ALERTS] "
        f"{ALERTS_FILE} "
        f"+{len(alerts)} records"
    )


# ============================================================
# Discord notification
# ============================================================

def send_discord(
    alert
):

    if not DISCORD_WEBHOOK_URL:

        print(
            "[DISCORD] "
            "DISCORD_WEBHOOK_URL is not configured."
        )

        return False

    icon = alert[
        "_icon"
    ]

    level_icon = alert[
        "_level_icon"
    ]

    level = alert[
        "level"
    ]

    contract = alert[
        "contract"
    ]

    option_type = alert[
        "option_type"
    ]

    strike = alert[
        "strike"
    ]

    qri_update_time = alert[
        "qri_update_time"
    ]

    volume_diff = alert[
        "volume_diff"
    ]

    oi_diff = alert[
        "oi_diff"
    ]

    current_volume = alert[
        "current_volume"
    ]

    current_oi = alert[
        "current_oi"
    ]

    current_price = alert[
        "current_price"
    ]

    iv = alert[
        "iv"
    ]

    reasons = alert[
        "reasons"
    ]

    # --------------------------------------------------------
    # Format numbers
    # --------------------------------------------------------

    def fmt(value):

        if value is None:
            return "-"

        if float(value).is_integer():

            return f"{int(value):,}"

        return f"{value:,.2f}"

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = (
        f"{level_icon} "
        f"{icon} **JPX OPTION {level}**\n"
        f"\n"
        f"**{contract} {option_type}**\n"
        f"Strike : **{strike}**\n"
        f"\n"
        f"📊 取引高差分 : **{fmt(volume_diff)}**\n"
        f"📦 OI差分 : **{fmt(oi_diff)}**\n"
        f"\n"
        f"取引高 : {fmt(current_volume)}\n"
        f"建玉残 : {fmt(current_oi)}\n"
        f"現在値 : {fmt(current_price)}\n"
        f"IV : {fmt(iv)}%\n"
        f"\n"
        f"🔎 判定 : {reasons}\n"
        f"🕐 QRI更新 : {qri_update_time}"
    )

    payload = {
        "content": message,
        "username": "JPX Option Monitor",
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=20,
        )

        print(
            f"[DISCORD] "
            f"HTTP {response.status_code}"
        )

        if response.status_code in (
            200,
            204,
        ):

            print(
                "[DISCORD] "
                "Notification sent."
            )

            return True

        print(
            f"[DISCORD ERROR] "
            f"{response.text}"
        )

        return False

    except requests.RequestException as e:

        print(
            f"[DISCORD ERROR] "
            f"{e}"
        )

        return False


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "========================================"
    )
    print(
        "LARGE TRADE DETECTOR"
    )
    print(
        "========================================"
    )

    print(
        f"Volume threshold : "
        f"{VOLUME_THRESHOLD}"
    )

    print(
        f"OI increase      : "
        f"{OI_INCREASE_THRESHOLD}"
    )

    print(
        f"OI decrease      : "
        f"{OI_DECREASE_THRESHOLD}"
    )

    # ========================================================
    # Load differences
    # ========================================================

    rows = load_differences()

    if not rows:

        print(
            "[INFO] "
            "No differences to analyze."
        )

        return

    # ========================================================
    # Detect
    # ========================================================

    alerts = detect_alerts(
        rows
    )

    print(
        f"[DETECTED] "
        f"{len(alerts)} alerts"
    )

    # ========================================================
    # Save
    # ========================================================

    save_alerts(
        alerts
    )

    # ========================================================
    # Discord
    # ========================================================

    if not alerts:

        return

    print()
    print(
        "========================================"
    )
    print(
        "DISCORD NOTIFICATIONS"
    )
    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Highest priority first
    # --------------------------------------------------------

    alerts.sort(
        key=lambda x:
            x.get(
                "_score",
                0
            ),
        reverse=True,
    )

    sent = 0

    for alert in alerts:

        print(
            f"[ALERT] "
            f"{alert['contract']} "
            f"{alert['option_type']} "
            f"{alert['strike']} "
            f"score={alert['_score']}"
        )

        if send_discord(
            alert
        ):

            sent += 1

    print()
    print(
        f"[DISCORD] "
        f"sent={sent}/{len(alerts)}"
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    main()
