import csv
import json
import os
import time
from pathlib import Path

import requests


# ============================================================
# Configuration
# ============================================================

DATA_DIR = Path("data")

CURRENT_FILE = DATA_DIR / "latest.csv"
PREVIOUS_FILE = DATA_DIR / "previous.csv"
DIFFERENCES_FILE = DATA_DIR / "differences.csv"

ALERT_HISTORY_FILE = DATA_DIR / "alert_history.json"


# ============================================================
# Discord
# ============================================================

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    ""
)


# ============================================================
# Alert settings
# ============================================================

# 大きな出来高増加
VOLUME_THRESHOLD = 100

# OI増加
OI_INCREASE_THRESHOLD = 100

# OI減少
OI_DECREASE_THRESHOLD = 100

# 価格変化
PRICE_CHANGE_THRESHOLD = 100

# IV変化
IV_CHANGE_THRESHOLD = 0.50


# ============================================================
# Volume gradient
# ============================================================

# 取引量に応じた表示
#
#     0～9       → ⚪ 小さい
#     10～49     → 🟢 やや大きい
#     50～99     → 🟡 大きい
#     100～199   → 🟠 非常に大きい
#     200以上    → 🔴 特大
#
# ============================================================

def volume_grade(volume):

    volume = abs(number(volume))

    if volume >= 200:
        return "🔴 特大"

    if volume >= 100:
        return "🟠 非常に大きい"

    if volume >= 50:
        return "🟡 大きい"

    if volume >= 10:
        return "🟢 やや大きい"

    return "⚪ 小さい"


# ============================================================
# Difference CSV columns
# ============================================================

DIFFERENCE_FIELDS = [

    "qri_update_time",
    "collected_at",

    "contract",
    "option_type",
    "strike",

    "previous_open_interest",
    "current_open_interest",
    "open_interest_diff",

    "previous_volume",
    "current_volume",
    "volume_diff",

    "previous_last_price",
    "current_last_price",
    "last_price_diff",

    "previous_iv",
    "current_iv",
    "iv_diff",

    "previous_ask_price",
    "current_ask_price",

    "previous_bid_price",
    "current_bid_price",

    "previous_ask_quantity",
    "current_ask_quantity",
    "ask_quantity_diff",

    "previous_bid_quantity",
    "current_bid_quantity",
    "bid_quantity_diff",

    "execution_side",

    "estimated_trade_value",

    "judgement",
    "judgement_score",

    "alert_type",
]


# ============================================================
# Utility
# ============================================================

def number(value):

    if value is None:
        return 0.0

    if value == "":
        return 0.0

    try:

        return float(
            str(value)
            .replace(",", "")
            .replace("%", "")
            .strip()
        )

    except Exception:

        return 0.0


# ============================================================
# Format number
# ============================================================

def fmt(value):

    try:

        value = float(value)

        if value.is_integer():

            return f"{int(value):,}"

        return f"{value:,.2f}"

    except Exception:

        return "-"


# ============================================================
# Format signed number
# ============================================================

def fmt_signed(value):

    try:

        value = float(value)

        if value > 0:

            if value.is_integer():

                return f"+{int(value):,}"

            return f"+{value:,.2f}"

        if value < 0:

            if value.is_integer():

                return f"{int(value):,}"

            return f"{value:,.2f}"

        return "0"

    except Exception:

        return "-"


# ============================================================
# Format money
# ============================================================

def format_money(value):

    value = abs(number(value))

    if value >= 100000000:

        return f"約{value / 100000000:.2f}億円"

    if value >= 10000:

        return f"約{value / 10000:.0f}万円"

    return f"約{value:,.0f}円"


# ============================================================
# Load CSV
# ============================================================

def load_csv(path):

    if not path.exists():

        print(
            f"[WARNING] {path} does not exist."
        )

        return []

    try:

        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            rows = list(
                csv.DictReader(f)
            )

        print(
            f"[LOAD] {path} "
            f"records={len(rows)}"
        )

        return rows

    except Exception as e:

        print(
            f"[ERROR] "
            f"Could not read {path}: {e}"
        )

        return []


# ============================================================
# Save differences
# ============================================================

def save_differences(differences):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        DIFFERENCES_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=DIFFERENCE_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()

        writer.writerows(
            differences
        )

    print(
        f"[SAVE] "
        f"{DIFFERENCES_FILE} "
        f"records={len(differences)}"
    )


# ============================================================
# Determine execution side
# ============================================================

def determine_execution_side(
    last_price,
    bid_price,
    ask_price,
):

    last_price = number(last_price)
    bid_price = number(bid_price)
    ask_price = number(ask_price)

    if last_price <= 0:

        return "判定困難"

    if bid_price > 0 and ask_price > 0:

        # Askで成立した可能性
        if last_price >= ask_price:

            return "Ask側"

        # Bidで成立した可能性
        if last_price <= bid_price:

            return "Bid側"

        # BidとAskの中間
        midpoint = (
            bid_price +
            ask_price
        ) / 2

        if last_price > midpoint:

            return "Ask寄り"

        if last_price < midpoint:

            return "Bid寄り"

        return "中間"

    return "判定困難"


# ============================================================
# Estimate trade value
# ============================================================

def estimate_trade_value(
    price,
    volume,
):

    price = number(price)
    volume = number(volume)

    if price <= 0 or volume <= 0:

        return 0

    # 日経225オプションは
    # 価格 × 1,000円 × 枚数
    #
    # 例：
    # 500円 × 1,000 × 100枚
    # = 5,000万円

    return (
        price *
        1000 *
        volume
    )


# ============================================================
# Determine judgement
# ============================================================

def determine_judgement(
    oi_diff,
    volume_diff,
    price_diff,
    iv_diff,
    execution_side,
):

    oi_diff = number(oi_diff)
    volume_diff = number(volume_diff)
    price_diff = number(price_diff)
    iv_diff = number(iv_diff)

    # --------------------------------------------------------
    # 出来高がない場合
    # --------------------------------------------------------

    if volume_diff <= 0:

        return (
            "判定困難",
            0,
        )


    # ========================================================
    # 新規ポジション
    # ========================================================

    if oi_diff > 0:

        # ----------------------------------------------------
        # Ask側
        # ----------------------------------------------------

        if execution_side in (
            "Ask側",
            "Ask寄り",
        ):

            score = 0

            score += 40

            if oi_diff >= 100:
                score += 20

            if price_diff > 0:
                score += 15

            if iv_diff > 0:
                score += 10

            if volume_diff >= 100:
                score += 15

            if score >= 80:

                level = "非常に高い"

            elif score >= 60:

                level = "高い"

            elif score >= 40:

                level = "中程度"

            else:

                level = "低い"

            return (
                f"新規買いポジション形成の可能性：{level}",
                score,
            )


        # ----------------------------------------------------
        # Bid側
        # ----------------------------------------------------

        if execution_side in (
            "Bid側",
            "Bid寄り",
        ):

            score = 0

            score += 40

            if oi_diff >= 100:
                score += 20

            if price_diff < 0:
                score += 15

            if iv_diff < 0:
                score += 10

            if volume_diff >= 100:
                score += 15

            if score >= 80:

                level = "非常に高い"

            elif score >= 60:

                level = "高い"

            elif score >= 40:

                level = "中程度"

            else:

                level = "低い"

            return (
                f"新規売りポジション形成の可能性：{level}",
                score,
            )


        return (
            "新規ポジション形成の可能性あり"
            "（買い・売り方向は判定困難）",
            40,
        )


    # ========================================================
    # 決済
    # ========================================================

    if oi_diff < 0:

        # ----------------------------------------------------
        # Bid側
        #
        # 既存の買いポジションを
        # 売って決済している可能性
        # ----------------------------------------------------

        if execution_side in (
            "Bid側",
            "Bid寄り",
        ):

            score = 0

            score += 40

            if abs(oi_diff) >= 100:
                score += 20

            if price_diff < 0:
                score += 15

            if volume_diff >= 100:
                score += 15

            if iv_diff < 0:
                score += 10

            if score >= 80:

                level = "非常に高い"

            elif score >= 60:

                level = "高い"

            elif score >= 40:

                level = "中程度"

            else:

                level = "低い"

            return (
                f"既存買いポジションの決済売りの可能性：{level}",
                score,
            )


        # ----------------------------------------------------
        # Ask側
        #
        # 既存の売りポジションを
        # 買って決済している可能性
        # ----------------------------------------------------

        if execution_side in (
            "Ask側",
            "Ask寄り",
        ):

            score = 0

            score += 40

            if abs(oi_diff) >= 100:
                score += 20

            if price_diff > 0:
                score += 15

            if volume_diff >= 100:
                score += 15

            if iv_diff > 0:
                score += 10

            if score >= 80:

                level = "非常に高い"

            elif score >= 60:

                level = "高い"

            elif score >= 40:

                level = "中程度"

            else:

                level = "低い"

            return (
                f"既存売りポジションの決済買いの可能性：{level}",
                score,
            )


        return (
            "決済の可能性あり"
            "（買い・売り方向は判定困難）",
            40,
        )


    # ========================================================
    # OI変化なし
    # ========================================================

    return (
        "出来高増加＋建玉ほぼ変化なし"
        " → 新規/決済の方向は判定困難",
        20,
    )


# ============================================================
# Calculate differences
# ============================================================

def calculate_differences(
    current_records,
    previous_records,
):

    print()
    print(
        "========================================"
    )
    print(
        "CALCULATING DIFFERENCE"
    )
    print(
        "========================================"
    )

    print(
        f"[CURRENT] records={len(current_records)}"
    )

    print(
        f"[PREVIOUS] records={len(previous_records)}"
    )


    previous_map = {}

    for row in previous_records:

        key = (
            row.get("contract", ""),
            row.get("option_type", ""),
            row.get("strike", ""),
        )

        previous_map[key] = row


    differences = []


    for current in current_records:

        key = (
            current.get("contract", ""),
            current.get("option_type", ""),
            current.get("strike", ""),
        )

        previous = previous_map.get(key)

        if previous is None:

            continue


        # ----------------------------------------------------
        # OI
        # ----------------------------------------------------

        previous_oi = number(
            previous.get("open_interest")
        )

        current_oi = number(
            current.get("open_interest")
        )

        oi_diff = (
            current_oi -
            previous_oi
        )


        # ----------------------------------------------------
        # Volume
        # ----------------------------------------------------

        previous_volume = number(
            previous.get("volume")
        )

        current_volume = number(
            current.get("volume")
        )

        volume_diff = (
            current_volume -
            previous_volume
        )


        # ----------------------------------------------------
        # Price
        # ----------------------------------------------------

        previous_price = number(
            previous.get("last_price")
        )

        current_price = number(
            current.get("last_price")
        )

        price_diff = (
            current_price -
            previous_price
        )


        # ----------------------------------------------------
        # IV
        # ----------------------------------------------------

        previous_iv = number(
            previous.get("iv")
        )

        current_iv = number(
            current.get("iv")
        )

        iv_diff = (
            current_iv -
            previous_iv
        )


        # ----------------------------------------------------
        # Bid / Ask
        # ----------------------------------------------------

        previous_ask_price = number(
            previous.get("ask_price")
        )

        current_ask_price = number(
            current.get("ask_price")
        )

        previous_bid_price = number(
            previous.get("bid_price")
        )

        current_bid_price = number(
            current.get("bid_price")
        )


        # ----------------------------------------------------
        # Quantity
        # ----------------------------------------------------

        previous_ask_qty = number(
            previous.get("ask_quantity")
        )

        current_ask_qty = number(
            current.get("ask_quantity")
        )

        previous_bid_qty = number(
            previous.get("bid_quantity")
        )

        current_bid_qty = number(
            current.get("bid_quantity")
        )


        ask_qty_diff = (
            current_ask_qty -
            previous_ask_qty
        )

        bid_qty_diff = (
            current_bid_qty -
            previous_bid_qty
        )


        # ----------------------------------------------------
        # Execution side
        # ----------------------------------------------------

        execution_side = determine_execution_side(
            current_price,
            current_bid_price,
            current_ask_price,
        )


        # ----------------------------------------------------
        # Estimated trade value
        # ----------------------------------------------------

        estimated_trade_value = (
            estimate_trade_value(
                current_price,
                volume_diff,
            )
        )


        # ----------------------------------------------------
        # Judgement
        # ----------------------------------------------------

        judgement, judgement_score = (
            determine_judgement(
                oi_diff,
                volume_diff,
                price_diff,
                iv_diff,
                execution_side,
            )
        )


        # ----------------------------------------------------
        # Alert type
        # ----------------------------------------------------

        alerts = []


        if volume_diff >= VOLUME_THRESHOLD:

            alerts.append(
                "VOLUME"
            )


        if oi_diff >= OI_INCREASE_THRESHOLD:

            alerts.append(
                "OI_INCREASE"
            )


        if oi_diff <= -OI_DECREASE_THRESHOLD:

            alerts.append(
                "OI_DECREASE"
            )


        if abs(price_diff) >= PRICE_CHANGE_THRESHOLD:

            alerts.append(
                "PRICE"
            )


        if abs(iv_diff) >= IV_CHANGE_THRESHOLD:

            alerts.append(
                "IV"
            )


        # ----------------------------------------------------
        # 新規/決済推定も通知対象にする
        # ----------------------------------------------------

        if (
            volume_diff > 0
            and oi_diff != 0
        ):

            alerts.append(
                "POSITION"
            )


        alert_type = ",".join(
            alerts
        )


        differences.append({

            "qri_update_time":
                current.get(
                    "qri_update_time",
                    ""
                ),

            "collected_at":
                current.get(
                    "collected_at",
                    ""
                ),

            "contract":
                current.get(
                    "contract",
                    ""
                ),

            "option_type":
                current.get(
                    "option_type",
                    ""
                ),

            "strike":
                current.get(
                    "strike",
                    ""
                ),

            "previous_open_interest":
                previous_oi,

            "current_open_interest":
                current_oi,

            "open_interest_diff":
                oi_diff,

            "previous_volume":
                previous_volume,

            "current_volume":
                current_volume,

            "volume_diff":
                volume_diff,

            "previous_last_price":
                previous_price,

            "current_last_price":
                current_price,

            "last_price_diff":
                price_diff,

            "previous_iv":
                previous_iv,

            "current_iv":
                current_iv,

            "iv_diff":
                iv_diff,

            "previous_ask_price":
                previous_ask_price,

            "current_ask_price":
                current_ask_price,

            "previous_bid_price":
                previous_bid_price,

            "current_bid_price":
                current_bid_price,

            "previous_ask_quantity":
                previous_ask_qty,

            "current_ask_quantity":
                current_ask_qty,

            "ask_quantity_diff":
                ask_qty_diff,

            "previous_bid_quantity":
                previous_bid_qty,

            "current_bid_quantity":
                current_bid_qty,

            "bid_quantity_diff":
                bid_qty_diff,

            "execution_side":
                execution_side,

            "estimated_trade_value":
                estimated_trade_value,

            "judgement":
                judgement,

            "judgement_score":
                judgement_score,

            "alert_type":
                alert_type,
        })


    print(
        f"[RESULT] records={len(differences)}"
    )

    return differences


# ============================================================
# Build Discord message
# ============================================================

def build_discord_message(
    difference
):

    contract = difference.get(
        "contract",
        ""
    )

    option_type = difference.get(
        "option_type",
        ""
    )

    strike = difference.get(
        "strike",
        ""
    )

    qri_update_time = difference.get(
        "qri_update_time",
        ""
    )

    oi_diff = number(
        difference.get(
            "open_interest_diff"
        )
    )

    volume_diff = number(
        difference.get(
            "volume_diff"
        )
    )

    price_diff = number(
        difference.get(
            "last_price_diff"
        )
    )

    iv_diff = number(
        difference.get(
            "iv_diff"
        )
    )

    estimated_trade_value = number(
        difference.get(
            "estimated_trade_value"
        )
    )

    execution_side = difference.get(
        "execution_side",
        "判定困難"
    )

    judgement = difference.get(
        "judgement",
        "判定困難"
    )

    alert_type = difference.get(
        "alert_type",
        ""
    )


    # ========================================================
    # Title
    # ========================================================

    if "POSITION" in alert_type:

        title = "🔥 大きな取引を検知"

    elif "VOLUME" in alert_type:

        title = "🔥 大きな取引を検知"

    elif "OI_INCREASE" in alert_type:

        title = "📊 建玉増加を検知"

    elif "OI_DECREASE" in alert_type:

        title = "📊 建玉減少を検知"

    elif "IV" in alert_type:

        title = "📈 IV変化を検知"

    elif "PRICE" in alert_type:

        title = "💹 オプション価格が大きく変化"

    else:

        title = "🔔 オプション変化を検知"


    # ========================================================
    # Message
    # ========================================================

    message = []

    message.append(
        "━━━━━━━━━━━━━━━━━━"
    )

    message.append(
        f"**{title}**"
    )

    message.append(
        f"【{contract}限 {option_type}】"
    )

    message.append(
        f"権利行使価格：**{fmt(strike)}円**"
    )

    if qri_update_time:

        message.append(
            f"変化時刻：{qri_update_time}"
        )

    message.append("")


    # ========================================================
    # Volume
    # ========================================================

    grade = volume_grade(
        volume_diff
    )

    message.append(
        f"📦 取引量："
        f"**{fmt_signed(volume_diff)}枚**"
        f" {grade}"
    )

    message.append("")


    # ========================================================
    # Estimated trade value
    # ========================================================

    if estimated_trade_value > 0:

        message.append(
            f"💰 概算取引金額："
            f"**{format_money(estimated_trade_value)}**"
        )

    else:

        message.append(
            "💰 概算取引金額：算出できません"
        )

    message.append("")


    # ========================================================
    # OI
    # ========================================================

    message.append(
        f"📊 建玉："
        f"**{fmt_signed(oi_diff)}枚**"
    )

    message.append("")


    # ========================================================
    # Price
    # ========================================================

    message.append(
        f"💴 価格："
        f"**{fmt_signed(price_diff)}円**"
    )

    message.append("")


    # ========================================================
    # IV
    # ========================================================

    if iv_diff > 0:

        iv_text = (
            f"📈 IV："
            f"**+{iv_diff:.2f}%**"
        )

    elif iv_diff < 0:

        iv_text = (
            f"📉 IV："
            f"**{iv_diff:.2f}%**"
        )

    else:

        iv_text = (
            "📊 IV：変化なし"
        )

    message.append(
        iv_text
    )

    message.append("")


    # ========================================================
    # Execution side
    # ========================================================

    if execution_side == "Ask側":

        execution_text = (
            "📈 約定方向：**Ask側の可能性**"
        )

    elif execution_side == "Bid側":

        execution_text = (
            "📉 約定方向：**Bid側の可能性**"
        )

    elif execution_side == "Ask寄り":

        execution_text = (
            "📈 約定方向：**Ask寄り**"
        )

    elif execution_side == "Bid寄り":

        execution_text = (
            "📉 約定方向：**Bid寄り**"
        )

    else:

        execution_text = (
            "↔️ 約定方向：**判定困難**"
        )

    message.append(
        execution_text
    )

    message.append("")


    # ========================================================
    # Judgement
    # ========================================================

    message.append(
        "🔎 **判定**"
    )

    message.append(
        judgement
    )

    message.append("")


    # ========================================================
    # Alert reason
    # ========================================================

    reasons = []

    if "VOLUME" in alert_type:

        reasons.append(
            "出来高増加"
        )

    if "OI_INCREASE" in alert_type:

        reasons.append(
            "建玉増加"
        )

    if "OI_DECREASE" in alert_type:

        reasons.append(
            "建玉減少"
        )

    if "PRICE" in alert_type:

        reasons.append(
            "価格変化"
        )

    if "IV" in alert_type:

        reasons.append(
            "IV変化"
        )

    if reasons:

        message.append(
            "🚨 **通知理由**"
        )

        message.append(
            " ＋ ".join(reasons)
        )

        message.append("")


    message.append(
        "━━━━━━━━━━━━━━━━━━"
    )


    return "\n".join(
        message
    )


# ============================================================
# Send Discord
# ============================================================

def send_discord_message(
    message
):

    if not DISCORD_WEBHOOK_URL:

        print(
            "[DISCORD] ERROR: "
            "Webhook URL is NOT configured."
        )

        return False


    try:

        response = requests.post(

            DISCORD_WEBHOOK_URL,

            json={
                "content": message
            },

            timeout=15,
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
            f"[DISCORD] ERROR: "
            f"HTTP {response.status_code}"
        )

        print(
            response.text
        )

        return False


    except Exception as e:

        print(
            f"[DISCORD] ERROR: {e}"
        )

        return False


# ============================================================
# Alert candidates
# ============================================================

def get_alert_candidates(
    differences
):

    candidates = []


    for row in differences:

        alert_type = row.get(
            "alert_type",
            ""
        )

        if not alert_type:

            continue

        candidates.append(
            row
        )


    # ========================================================
    # Priority
    # ========================================================

    def priority(row):

        alert_type = row.get(
            "alert_type",
            ""
        )

        score = 0


        if "POSITION" in alert_type:

            score += 1000


        if "OI_INCREASE" in alert_type:

            score += 500


        if "OI_DECREASE" in alert_type:

            score += 450


        if "VOLUME" in alert_type:

            score += 300


        if "IV" in alert_type:

            score += 200


        if "PRICE" in alert_type:

            score += 100


        score += abs(
            number(
                row.get(
                    "volume_diff"
                )
            )
        )

        score += abs(
            number(
                row.get(
                    "open_interest_diff"
                )
            )
        )


        return score


    candidates.sort(
        key=priority,
        reverse=True
    )


    return candidates


# ============================================================
# Send alerts
# ============================================================

def send_alerts(
    differences
):

    print()
    print(
        "========================================"
    )

    print(
        "DISCORD ALERT"
    )

    print(
        "========================================"
    )


    if not DISCORD_WEBHOOK_URL:

        print(
            "[DISCORD] "
            "Webhook URL is NOT configured."
        )

        return 0


    print(
        "[DISCORD] "
        "Webhook URL is configured."
    )


    candidates = get_alert_candidates(
        differences
    )


    print(
        f"Alert candidates: "
        f"{len(candidates)}"
    )


    if not candidates:

        print(
            "[DISCORD] "
            "No alert candidates."
        )

        return 0


    sent_count = 0


    for difference in candidates:

        message = build_discord_message(
            difference
        )


        print()

        print(
            f"[ALERT {sent_count + 1}]"
        )

        print(
            f"{difference.get('contract', '')} "
            f"{difference.get('option_type', '')} "
            f"{difference.get('strike', '')}"
        )

        print(
            f"Volume diff: "
            f"{fmt_signed(difference.get('volume_diff'))}"
        )

        print(
            f"OI diff: "
            f"{fmt_signed(difference.get('open_interest_diff'))}"
        )

        print(
            f"Price diff: "
            f"{fmt_signed(difference.get('last_price_diff'))}"
        )

        print(
            f"IV diff: "
            f"{fmt_signed(difference.get('iv_diff'))}"
        )

        print(
            f"Execution: "
            f"{difference.get('execution_side', '')}"
        )

        print(
            f"Judgement: "
            f"{difference.get('judgement', '')}"
        )


        success = send_discord_message(
            message
        )


        if success:

            sent_count += 1

        else:

            print(
                "[DISCORD] "
                "Failed to send alert."
            )


        time.sleep(
            0.5
        )


    return sent_count


# ============================================================
# Save previous
# ============================================================

def save_previous(
    current_records
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    if not current_records:

        return


    with open(
        PREVIOUS_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        fieldnames = list(
            current_records[0].keys()
        )

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            current_records
        )


    print(
        f"[SAVE] "
        f"{PREVIOUS_FILE} "
        f"records={len(current_records)}"
    )


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "========================================"
    )

    print(
        "CALCULATE DIFFERENCES"
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # Current
    # --------------------------------------------------------

    current_records = load_csv(
        CURRENT_FILE
    )


    if not current_records:

        raise RuntimeError(
            "latest.csv is empty."
        )


    # --------------------------------------------------------
    # Previous
    # --------------------------------------------------------

    previous_records = load_csv(
        PREVIOUS_FILE
    )


    # --------------------------------------------------------
    # First run
    # --------------------------------------------------------

    if not previous_records:

        print()

        print(
            "[INFO] "
            "previous.csv is empty or does not exist."
        )

        print(
            "[INFO] "
            "Creating previous.csv."
        )


        save_previous(
            current_records
        )


        save_differences(
            []
        )


        print()

        print(
            "========================================"
        )

        print(
            "FIRST RUN COMPLETE"
        )

        print(
            "========================================"
        )

        return


    # --------------------------------------------------------
    # Calculate
    # --------------------------------------------------------

    differences = calculate_differences(

        current_records,

        previous_records,
    )


    # --------------------------------------------------------
    # Save differences
    # --------------------------------------------------------

    save_differences(
        differences
    )


    # --------------------------------------------------------
    # Discord
    # --------------------------------------------------------

    alert_count = send_alerts(
        differences
    )


    # --------------------------------------------------------
    # Update previous
    # --------------------------------------------------------

    save_previous(
        current_records
    )


    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    candidates = get_alert_candidates(
        differences
    )


    print()

    print(
        "========================================"
    )

    print(
        "DIFFERENCE COMPLETE"
    )

    print(
        f"Current records: "
        f"{len(current_records)}"
    )

    print(
        f"Previous records: "
        f"{len(previous_records)}"
    )

    print(
        f"Difference records: "
        f"{len(differences)}"
    )

    print(
        f"Alert candidates: "
        f"{len(candidates)}"
    )

    print(
        f"Alerts sent: "
        f"{alert_count}"
    )

    print(
        "========================================"
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    main()
