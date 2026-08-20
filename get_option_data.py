import csv
import re
import time
import os

from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# Configuration
# ============================================================

CONTRACTS = {
    "2026-09": "https://svc.qri.jp/jpx/nkopm/",
    "2026-10": "https://svc.qri.jp/jpx/nkopm/1",
    "2026-12": "https://svc.qri.jp/jpx/nkopm/2",
}


DATA_DIR = Path("data")
HISTORY_DIR = DATA_DIR / "history"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

HISTORY_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


LATEST_FILE = DATA_DIR / "latest.csv"
DIFFERENCES_FILE = DATA_DIR / "differences.csv"


JST = timezone(
    timedelta(hours=9)
)


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

# 1回の更新で出来高がこの数量以上増加したら通知
VOLUME_THRESHOLD = 100

# 建玉残がこの数量以上増加したら通知
OI_INCREASE_THRESHOLD = 100

# 建玉残がこの数量以上減少したら通知
OI_DECREASE_THRESHOLD = 100

# 最終価格がこの金額以上変化したら通知
PRICE_CHANGE_THRESHOLD = 100

# 1回の実行でDiscordへ送る最大件数
MAX_DISCORD_ALERTS = 20

# Discord連続送信間隔
DISCORD_INTERVAL = 0.5


# ============================================================
# CSV columns
# ============================================================

FIELDNAMES = [
    "qri_update_time",
    "collected_at",
    "trading_day",
    "last_trading_day",
    "contract",
    "option_type",
    "strike",
    "settlement",
    "open_interest",
    "volume",
    "ask_iv",
    "bid_iv",
    "ask_price",
    "ask_quantity",
    "bid_price",
    "bid_quantity",
    "iv",
    "change",
    "change_percent",
    "last_price",
    "trade_time",
]


# ============================================================
# Difference columns
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

    "previous_ask_quantity",
    "current_ask_quantity",
    "ask_quantity_diff",

    "previous_bid_quantity",
    "current_bid_quantity",
    "bid_quantity_diff",

    "alert_type",
]


# ============================================================
# HTTP Session
# ============================================================

session = requests.Session()

session.headers.update({

    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 "
        "Safari/537.36"
    ),

    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,"
        "image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),

    "Accept-Language": (
        "ja-JP,ja;q=0.9,"
        "en-US;q=0.8,en;q=0.7"
    ),

    "Accept-Encoding": (
        "gzip, deflate, br"
    ),

    "Connection": "keep-alive",

    "Upgrade-Insecure-Requests": "1",
})


# ============================================================
# Text cleanup
# ============================================================

def clean_text(text):

    if text is None:
        return ""

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# Number conversion
# ============================================================

def to_number(text):

    text = clean_text(text)

    if not text:
        return None

    if text in (
        "-",
        "--",
        "－",
        "―",
    ):
        return None

    text = text.replace(
        ",",
        ""
    )

    text = text.replace(
        "%",
        ""
    )

    try:

        value = float(text)

        if value.is_integer():
            return int(value)

        return value

    except ValueError:

        return None


# ============================================================
# Extract first numeric value
# ============================================================

def extract_number(text):

    text = clean_text(text)

    if not text:
        return None

    match = re.search(
        r"-?[\d,]+(?:\.\d+)?",
        text,
    )

    if not match:
        return None

    return to_number(
        match.group(0)
    )


# ============================================================
# Price + time
# ============================================================

def parse_price_and_time(cell):

    if cell is None:

        return (
            None,
            None,
        )

    text = clean_text(
        cell.get_text(
            " ",
            strip=True,
        )
    )

    if not text:

        return (
            None,
            None,
        )

    lines = [
        clean_text(x)
        for x in cell.stripped_strings
    ]

    lines = [
        x
        for x in lines
        if x
    ]

    price = None

    if lines:

        price = extract_number(
            lines[0]
        )

    trade_time = None

    for line in lines[1:]:

        if re.search(
            r"\d{1,2}/\d{1,2}",
            line,
        ):

            trade_time = line

            break

    return (
        price,
        trade_time,
    )


# ============================================================
# Parse two values
# ============================================================

def parse_two_values(cell):

    if cell is None:

        return (
            None,
            None,
        )

    lines = [
        clean_text(x)
        for x in cell.stripped_strings
    ]

    lines = [
        x
        for x in lines
        if x
    ]

    first = (
        extract_number(lines[0])
        if len(lines) >= 1
        else None
    )

    second = (
        extract_number(lines[1])
        if len(lines) >= 2
        else None
    )

    return (
        first,
        second,
    )


# ============================================================
# Quote parser
# ============================================================

def parse_quote(cell):

    if cell is None:

        return (
            None,
            None,
            None,
            None,
        )

    lines = [
        clean_text(x)
        for x in cell.stripped_strings
    ]

    lines = [
        x
        for x in lines
        if x
    ]

    ask_price = None
    ask_quantity = None

    bid_price = None
    bid_quantity = None

    # ASK
    if len(lines) >= 1:

        match = re.search(
            r"(.+?)\s*\((.*?)\)",
            lines[0],
        )

        if match:

            ask_price = extract_number(
                match.group(1)
            )

            ask_quantity = extract_number(
                match.group(2)
            )

        else:

            ask_price = extract_number(
                lines[0]
            )

    # BID
    if len(lines) >= 2:

        match = re.search(
            r"(.+?)\s*\((.*?)\)",
            lines[1],
        )

        if match:

            bid_price = extract_number(
                match.group(1)
            )

            bid_quantity = extract_number(
                match.group(2)
            )

        else:

            bid_price = extract_number(
                lines[1]
            )

    return (
        ask_price,
        ask_quantity,
        bid_price,
        bid_quantity,
    )


# ============================================================
# Fetch QRI HTML
# ============================================================

def fetch_html(url):

    print()
    print(
        f"[GET] {url}"
    )

    last_error = None

    for attempt in range(1, 4):

        try:

            response = session.get(
                url,
                headers={
                    "Referer":
                        "https://svc.qri.jp/jpx/nkopm/",
                },
                timeout=30,
                allow_redirects=True,
            )

            print(
                f"[HTTP] "
                f"attempt={attempt} "
                f"status={response.status_code} "
                f"url={response.url}"
            )

            if response.status_code == 200:

                response.encoding = "utf-8"

                return response.text

            if response.status_code in (
                429,
                500,
                502,
                503,
                504,
            ):

                last_error = (
                    f"HTTP "
                    f"{response.status_code}"
                )

                print(
                    f"[RETRY] "
                    f"{last_error}"
                )

                if attempt < 3:

                    time.sleep(
                        attempt * 3
                    )

                    continue

                break

            response.raise_for_status()

        except requests.RequestException as e:

            last_error = e

            print(
                f"[ERROR] "
                f"attempt={attempt}: "
                f"{e}"
            )

            if attempt < 3:

                time.sleep(
                    attempt * 3
                )

    raise RuntimeError(
        f"Failed to fetch QRI page "
        f"after 3 attempts: "
        f"{url} / {last_error}"
    )


# ============================================================
# QRI update time
# ============================================================

def get_qri_update_time(soup):

    element = soup.select_one(
        ".update-time dd"
    )

    if not element:

        raise RuntimeError(
            "QRI update time not found."
        )

    return clean_text(
        element.get_text(
            " ",
            strip=True,
        )
    )


# ============================================================
# Contract info
# ============================================================

def get_contract_info(soup):

    trading_day = ""
    last_trading_day = ""

    areas = soup.select(
        ".date-table"
    )

    for area in areas:

        dt = area.select_one("dt")
        dd = area.select_one("dd")

        if not dt or not dd:
            continue

        label = clean_text(
            dt.get_text(
                " ",
                strip=True,
            )
        )

        value = clean_text(
            dd.get_text(
                " ",
                strip=True,
            )
        )

        if label == "取引日":

            trading_day = value

        elif label == "取引最終日":

            last_trading_day = value

    return (
        trading_day,
        last_trading_day,
    )


# ============================================================
# Parse option table
# ============================================================

def parse_option_table(
    soup,
    contract,
    qri_update_time,
    collected_at,
    trading_day,
    last_trading_day,
):

    table = soup.select_one(
        "table.price-table"
    )

    if not table:

        raise RuntimeError(
            f"price-table not found: {contract}"
        )

    tbody = table.select_one(
        "tbody.price-info-scroll"
    )

    if not tbody:

        raise RuntimeError(
            f"price-info-scroll not found: {contract}"
        )

    rows = tbody.find_all(
        "tr",
        recursive=False,
    )

    print(
        f"[TABLE] {contract}: "
        f"{len(rows)} rows"
    )

    records = []

    for row in rows:

        classes = row.get(
            "class",
            [],
        )

        if "greek" in classes:
            continue

        cells = row.find_all(
            "td",
            recursive=False,
        )

        if len(cells) < 17:
            continue

        # ====================================================
        # CALL
        # ====================================================

        call_settlement = extract_number(
            cells[0].get_text(
                " ",
                strip=True,
            )
        )

        call_oi = extract_number(
            cells[1].get_text(
                " ",
                strip=True,
            )
        )

        call_volume = extract_number(
            cells[2].get_text(
                " ",
                strip=True,
            )
        )

        call_ask_iv, call_bid_iv = (
            parse_two_values(
                cells[3]
            )
        )

        (
            call_ask_price,
            call_ask_quantity,
            call_bid_price,
            call_bid_quantity,
        ) = parse_quote(
            cells[4]
        )

        call_iv = extract_number(
            cells[5].get_text(
                " ",
                strip=True,
            )
        )

        call_change, call_change_percent = (
            parse_two_values(
                cells[6]
            )
        )

        call_last_price, call_trade_time = (
            parse_price_and_time(
                cells[7]
            )
        )

        # ====================================================
        # STRIKE
        # ====================================================

        strike_text = clean_text(
            cells[8].get_text(
                " ",
                strip=True,
            )
        )

        strike_match = re.search(
            r"[\d,]+(?:\.\d+)?",
            strike_text,
        )

        if not strike_match:
            continue

        strike = to_number(
            strike_match.group(0)
        )

        if strike is None:
            continue

        # ====================================================
        # PUT
        # ====================================================

        put_last_price, put_trade_time = (
            parse_price_and_time(
                cells[9]
            )
        )

        put_change, put_change_percent = (
            parse_two_values(
                cells[10]
            )
        )

        put_iv = extract_number(
            cells[11].get_text(
                " ",
                strip=True,
            )
        )

        (
            put_ask_price,
            put_ask_quantity,
            put_bid_price,
            put_bid_quantity,
        ) = parse_quote(
            cells[12]
        )

        put_ask_iv, put_bid_iv = (
            parse_two_values(
                cells[13]
            )
        )

        put_volume = extract_number(
            cells[14].get_text(
                " ",
                strip=True,
            )
        )

        put_oi = extract_number(
            cells[15].get_text(
                " ",
                strip=True,
            )
        )

        put_settlement = extract_number(
            cells[16].get_text(
                " ",
                strip=True,
            )
        )

        # ====================================================
        # Common
        # ====================================================

        common = {

            "qri_update_time":
                qri_update_time,

            "collected_at":
                collected_at,

            "trading_day":
                trading_day,

            "last_trading_day":
                last_trading_day,

            "contract":
                contract,

            "strike":
                strike,
        }

        # ====================================================
        # CALL record
        # ====================================================

        call_record = {
            **common,

            "option_type":
                "CALL",

            "settlement":
                call_settlement,

            "open_interest":
                call_oi,

            "volume":
                call_volume,

            "ask_iv":
                call_ask_iv,

            "bid_iv":
                call_bid_iv,

            "ask_price":
                call_ask_price,

            "ask_quantity":
                call_ask_quantity,

            "bid_price":
                call_bid_price,

            "bid_quantity":
                call_bid_quantity,

            "iv":
                call_iv,

            "change":
                call_change,

            "change_percent":
                call_change_percent,

            "last_price":
                call_last_price,

            "trade_time":
                call_trade_time,
        }

        # ====================================================
        # PUT record
        # ====================================================

        put_record = {
            **common,

            "option_type":
                "PUT",

            "settlement":
                put_settlement,

            "open_interest":
                put_oi,

            "volume":
                put_volume,

            "ask_iv":
                put_ask_iv,

            "bid_iv":
                put_bid_iv,

            "ask_price":
                put_ask_price,

            "ask_quantity":
                put_ask_quantity,

            "bid_price":
                put_bid_price,

            "bid_quantity":
                put_bid_quantity,

            "iv":
                put_iv,

            "change":
                put_change,

            "change_percent":
                put_change_percent,

            "last_price":
                put_last_price,

            "trade_time":
                put_trade_time,
        }

        records.append(
            call_record
        )

        records.append(
            put_record
        )

    return records


# ============================================================
# Get contract data
# ============================================================

def get_contract_data(
    contract,
    url,
    collected_at,
):

    html = fetch_html(
        url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title = clean_text(
        soup.title.get_text()
        if soup.title
        else ""
    )

    print(
        f"[TITLE] {title}"
    )

    qri_update_time = get_qri_update_time(
        soup
    )

    print(
        f"[QRI UPDATE] "
        f"{qri_update_time}"
    )

    (
        trading_day,
        last_trading_day,
    ) = get_contract_info(
        soup
    )

    print(
        f"[TRADING DAY] "
        f"{trading_day}"
    )

    print(
        f"[LAST TRADING DAY] "
        f"{last_trading_day}"
    )

    records = parse_option_table(
        soup=soup,
        contract=contract,
        qri_update_time=qri_update_time,
        collected_at=collected_at,
        trading_day=trading_day,
        last_trading_day=last_trading_day,
    )

    print(
        f"[OK] {contract} "
        f"records={len(records)}"
    )

    return (
        qri_update_time,
        records,
    )


# ============================================================
# Load CSV
# ============================================================

def load_csv(path):

    if not path.exists():
        return []

    try:

        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            return list(
                csv.DictReader(f)
            )

    except Exception as e:

        print(
            f"[WARNING] "
            f"Could not read {path}: {e}"
        )

        return []


# ============================================================
# Save latest
# ============================================================

def save_latest(records):

    if not records:

        raise RuntimeError(
            "Cannot save empty latest.csv"
        )

    with open(
        LATEST_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES,
        )

        writer.writeheader()
        writer.writerows(records)

    print(
        f"[LATEST] "
        f"{LATEST_FILE} "
        f"records={len(records)}"
    )


# ============================================================
# Previous update times
# ============================================================

def get_previous_update_times(records):

    result = {}

    for row in records:

        contract = row.get(
            "contract"
        )

        update_time = row.get(
            "qri_update_time"
        )

        if contract and update_time:

            result[contract] = update_time

    return result


# ============================================================
# History filename
# ============================================================

def get_history_file(trading_day):

    match = re.search(
        r"(\d{4})/(\d{2})/(\d{2})",
        trading_day,
    )

    if match:

        date_string = (
            f"{match.group(1)}-"
            f"{match.group(2)}-"
            f"{match.group(3)}"
        )

    else:

        date_string = datetime.now(
            JST
        ).strftime(
            "%Y-%m-%d"
        )

    return (
        HISTORY_DIR /
        f"{date_string}.csv"
    )


# ============================================================
# Save history
# ============================================================

def save_history(
    records,
    trading_day,
):

    if not records:
        return

    history_file = get_history_file(
        trading_day
    )

    existing_keys = set()

    if history_file.exists():

        with open(
            history_file,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                key = (
                    row.get("contract", ""),
                    row.get("option_type", ""),
                    row.get("strike", ""),
                    row.get("qri_update_time", ""),
                )

                existing_keys.add(
                    key
                )

    new_records = []

    for record in records:

        key = (
            record["contract"],
            record["option_type"],
            str(record["strike"]),
            record["qri_update_time"],
        )

        if key not in existing_keys:

            new_records.append(
                record
            )

    if not new_records:

        print(
            "[HISTORY] No new records."
        )

        return

    file_exists = history_file.exists()

    with open(
        history_file,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES,
        )

        if not file_exists:

            writer.writeheader()

        writer.writerows(
            new_records
        )

    print(
        f"[HISTORY] "
        f"{history_file} "
        f"+{len(new_records)} records"
    )


# ============================================================
# Numeric helper
# ============================================================

def number(value):

    if value is None:
        return 0

    if value == "":
        return 0

    try:

        return float(
            str(value).replace(
                ",",
                ""
            )
        )

    except Exception:

        return 0


# ============================================================
# Format number
# ============================================================

def fmt(value):

    if value is None:
        return "-"

    try:

        value = float(value)

        if value.is_integer():

            return f"{int(value):,}"

        return f"{value:,.2f}"

    except Exception:

        return str(value)


# ============================================================
# Calculate differences
# ============================================================

def calculate_differences(
    previous_records,
    current_records,
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
        f"[CURRENT] records="
        f"{len(current_records)}"
    )

    print(
        f"[PREVIOUS] records="
        f"{len(previous_records)}"
    )

    previous_map = {}

    for row in previous_records:

        key = (
            row.get(
                "contract",
                ""
            ),
            row.get(
                "option_type",
                ""
            ),
            row.get(
                "strike",
                ""
            ),
        )

        previous_map[key] = row

    differences = []

    for current in current_records:

        key = (
            current.get(
                "contract",
                ""
            ),
            current.get(
                "option_type",
                ""
            ),
            current.get(
                "strike",
                ""
            ),
        )

        previous = previous_map.get(
            key
        )

        if previous is None:
            continue

        previous_oi = number(
            previous.get(
                "open_interest"
            )
        )

        current_oi = number(
            current.get(
                "open_interest"
            )
        )

        previous_volume = number(
            previous.get(
                "volume"
            )
        )

        current_volume = number(
            current.get(
                "volume"
            )
        )

        previous_price = number(
            previous.get(
                "last_price"
            )
        )

        current_price = number(
            current.get(
                "last_price"
            )
        )

        previous_ask_qty = number(
            previous.get(
                "ask_quantity"
            )
        )

        current_ask_qty = number(
            current.get(
                "ask_quantity"
            )
        )

        previous_bid_qty = number(
            previous.get(
                "bid_quantity"
            )
        )

        current_bid_qty = number(
            current.get(
                "bid_quantity"
            )
        )

        oi_diff = (
            current_oi -
            previous_oi
        )

        volume_diff = (
            current_volume -
            previous_volume
        )

        price_diff = (
            current_price -
            previous_price
        )

        ask_qty_diff = (
            current_ask_qty -
            previous_ask_qty
        )

        bid_qty_diff = (
            current_bid_qty -
            previous_bid_qty
        )

        alerts = []

        # ====================================================
        # Volume
        # ====================================================

        if (
            volume_diff
            >= VOLUME_THRESHOLD
        ):

            alerts.append(
                "VOLUME"
            )

        # ====================================================
        # OI increase
        # ====================================================

        if (
            oi_diff
            >= OI_INCREASE_THRESHOLD
        ):

            alerts.append(
                "OI_INCREASE"
            )

        # ====================================================
        # OI decrease
        # ====================================================

        if (
            oi_diff
            <= -OI_DECREASE_THRESHOLD
        ):

            alerts.append(
                "OI_DECREASE"
            )

        # ====================================================
        # Price
        # ====================================================

        if (
            abs(price_diff)
            >= PRICE_CHANGE_THRESHOLD
        ):

            alerts.append(
                "PRICE"
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

            "alert_type":
                alert_type,
        })

    print(
        f"[RESULT] records="
        f"{len(differences)}"
    )

    return differences


# ============================================================
# Save differences
# ============================================================

def save_differences(
    differences
):

    if not differences:

        print(
            "[DIFFERENCE] "
            "No difference records."
        )

        return

    with open(
        DIFFERENCES_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=DIFFERENCE_FIELDS,
        )

        writer.writeheader()

        writer.writerows(
            differences
        )

    print(
        f"[DIFFERENCE] "
        f"{DIFFERENCES_FILE} "
        f"records={len(differences)}"
    )


# ============================================================
# Discord webhook
# ============================================================

def send_discord_message(
    message
):

    if not DISCORD_WEBHOOK_URL:

        print(
            "[DISCORD] ERROR: "
            "DISCORD_WEBHOOK_URL is not set."
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
            f"[DISCORD] ERROR: "
            f"{e}"
        )

        return False


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

    current_oi = number(
        difference.get(
            "current_open_interest"
        )
    )

    current_volume = number(
        difference.get(
            "current_volume"
        )
    )

    current_price = number(
        difference.get(
            "current_last_price"
        )
    )

    alert_type = difference.get(
        "alert_type",
        ""
    )

    # ========================================================
    # Emoji
    # ========================================================

    if "OI_INCREASE" in alert_type:

        emoji = "🟢"

    elif "OI_DECREASE" in alert_type:

        emoji = "🔴"

    elif "VOLUME" in alert_type:

        emoji = "📊"

    elif "PRICE" in alert_type:

        emoji = "💹"

    else:

        emoji = "⚠️"

    # ========================================================
    # Direction
    # ========================================================

    if oi_diff > 0:

        oi_direction = "増加"

    elif oi_diff < 0:

        oi_direction = "減少"

    else:

        oi_direction = "変化なし"

    if volume_diff > 0:

        volume_direction = "増加"

    elif volume_diff < 0:

        volume_direction = "減少"

    else:

        volume_direction = "変化なし"

    if price_diff > 0:

        price_direction = "上昇"

    elif price_diff < 0:

        price_direction = "下落"

    else:

        price_direction = "変化なし"

    # ========================================================
    # Message
    # ========================================================

    message = (
        f"{emoji} **JPX OPTION ALERT**\n"
        f"\n"
        f"**{contract} {option_type} "
        f"{fmt(strike)}**\n"
        f"\n"
        f"Alert: `{alert_type}`\n"
        f"\n"
        f"📌 建玉残(OI)\n"
        f"現在: `{fmt(current_oi)}`\n"
        f"差分: `{fmt(oi_diff)}` "
        f"({oi_direction})\n"
        f"\n"
        f"📊 出来高\n"
        f"現在: `{fmt(current_volume)}`\n"
        f"差分: `+{fmt(volume_diff)}` "
        f"({volume_direction})\n"
        f"\n"
        f"💹 最終価格\n"
        f"現在: `{fmt(current_price)}`\n"
        f"差分: `{fmt(price_diff)}` "
        f"({price_direction})\n"
    )

    return message


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

    # ========================================================
    # Webhook check
    # ========================================================

    if DISCORD_WEBHOOK_URL:

        print(
            "[DISCORD] "
            "Webhook URL is configured."
        )

    else:

        print(
            "[DISCORD] "
            "Webhook URL is NOT configured."
        )

    # ========================================================
    # Alert candidates
    # ========================================================

    alert_records = [
        row
        for row in differences
        if row.get(
            "alert_type",
            ""
        )
    ]

    print(
        f"Alert candidates: "
        f"{len(alert_records)}"
    )

    if not alert_records:

        print(
            "[DISCORD] "
            "No alert candidates."
        )

        return

    # ========================================================
    # Limit
    # ========================================================

    alert_records = alert_records[
        :MAX_DISCORD_ALERTS
    ]

    # ========================================================
    # Send
    # ========================================================

    for index, difference in enumerate(
        alert_records,
        start=1
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

        alert_type = difference.get(
            "alert_type",
            ""
        )

        print()
        print(
            f"[ALERT {index}/"
            f"{len(alert_records)}]"
        )

        print(
            f"{contract} "
            f"{option_type} "
            f"{fmt(strike)}"
        )

        print(
            f"OI diff: "
            f"{fmt(oi_diff)}"
        )

        print(
            f"Volume diff: "
            f"{fmt(volume_diff)}"
        )

        print(
            f"Price diff: "
            f"{fmt(price_diff)}"
        )

        print(
            f"Alert type: "
            f"{alert_type}"
        )

        message = build_discord_message(
            difference
        )

        success = send_discord_message(
            message
        )

        if not success:

            print(
                "[DISCORD] "
                "Failed to send alert."
            )

        time.sleep(
            DISCORD_INTERVAL
        )


# ============================================================
# Main
# ============================================================

def main():

    collected_at = (
        datetime.now(
            timezone.utc
        )
        .astimezone(
            JST
        )
        .isoformat(
            timespec="seconds"
        )
    )

    print()
    print(
        "========================================"
    )
    print(
        "JPX OPTION DATA"
    )
    print(
        "========================================"
    )

    print(
        f"Collected at: "
        f"{collected_at}"
    )

    print(
        "========================================"
    )

    # ========================================================
    # Load previous latest.csv
    # ========================================================

    previous_records = load_csv(
        LATEST_FILE
    )

    print(
        f"[PREVIOUS] "
        f"latest.csv records="
        f"{len(previous_records)}"
    )

    previous_update_times = (
        get_previous_update_times(
            previous_records
        )
    )

    # ========================================================
    # Fetch QRI
    # ========================================================

    all_records = []

    contract_update_times = {}

    for contract, url in CONTRACTS.items():

        try:

            (
                qri_update_time,
                records,
            ) = get_contract_data(
                contract,
                url,
                collected_at,
            )

            contract_update_times[
                contract
            ] = qri_update_time

            all_records.extend(
                records
            )

        except Exception as e:

            print(
                f"[ERROR] "
                f"{contract}: {e}"
            )

    # ========================================================
    # Data validation
    # ========================================================

    if not all_records:

        raise RuntimeError(
            "No option data collected."
        )

    print()
    print(
        f"[CURRENT] records="
        f"{len(all_records)}"
    )

    # ========================================================
    # QRI update check
    # ========================================================

    new_records = []

    qri_updated = False

    for contract in CONTRACTS.keys():

        current_time = (
            contract_update_times.get(
                contract
            )
        )

        previous_time = (
            previous_update_times.get(
                contract
            )
        )

        print()
        print(
            "----------------------------------------"
        )

        print(
            f"[CHECK] {contract}"
        )

        print(
            f"Previous: "
            f"{previous_time}"
        )

        print(
            f"Current : "
            f"{current_time}"
        )

        if (
            current_time
            and
            current_time != previous_time
        ):

            print(
                f"[NEW] {contract}"
            )

            qri_updated = True

            for record in all_records:

                if (
                    record.get(
                        "contract"
                    )
                    == contract
                ):

                    new_records.append(
                        record
                    )

        else:

            print(
                f"[NO CHANGE] "
                f"{contract}"
            )

    # ========================================================
    # Calculate differences
    # ========================================================

    differences = calculate_differences(
        previous_records,
        all_records,
    )

    save_differences(
        differences
    )

    # ========================================================
    # Discord notification
    # ========================================================

    if qri_updated:

        print()
        print(
            "[QRI] "
            "New QRI update detected."
        )

        send_alerts(
            differences
        )

    else:

        print()
        print(
            "[QRI] "
            "No new QRI update."
        )

    # ========================================================
    # Save latest
    # ========================================================

    save_latest(
        all_records
    )

    # ========================================================
    # Save history
    # ========================================================

    if new_records:

        trading_day = (
            new_records[0].get(
                "trading_day",
                ""
            )
        )

        save_history(
            new_records,
            trading_day,
        )

    # ========================================================
    # Summary
    # ========================================================

    print()
    print(
        "========================================"
    )
    print(
        "SUMMARY"
    )
    print(
        "========================================"
    )

    print(
        f"Total records: "
        f"{len(all_records)}"
    )

    print(
        f"New records: "
        f"{len(new_records)}"
    )

    print(
        f"Difference records: "
        f"{len(differences)}"
    )

    print(
        f"Latest file: "
        f"{LATEST_FILE}"
    )

    print(
        f"Difference file: "
        f"{DIFFERENCES_FILE}"
    )

    print(
        "========================================"
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    main()
