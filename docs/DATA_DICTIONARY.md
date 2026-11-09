# CSVデータ項目・保存仕様

最終更新日：2026-11-05（欠損値の取り扱いを更新）

## 1. 最新データ

ファイル：`data/latest.csv`

現行コードの `FIELDNAMES` に基づく列一覧です。`open_interest_status` は2026-11-09追加列です。旧CSVではこの列が存在しない場合があります。

| 列名 | 意味 | 注意点 |
|---|---|---|
| `qri_update_time` | QRIページの更新時刻 | QRI側の時刻。取得時刻とは異なる |
| `collected_at` | プログラムが取得した日時 | JSTオフセット付きISO形式 |
| `trading_day` | QRIが示す取引日 | 夜間取引では暦日と異なる場合がある |
| `last_trading_day` | 限月の最終取引日 | QRIページから取得 |
| `contract` | 限月（YYYY-MM） | 例：2026-12 |
| `option_type` | CALLまたはPUT | 種別 |
| `strike` | 権利行使価格 | 数値 |
| `settlement` | 清算値 | QRI表示値 |
| `open_interest` | 建玉残高（OI） | 空欄は0と同義ではない |
| `volume` | 出来高 | 空欄は0と同義ではない |
| `ask_iv` | Ask側IV | 欠損値の扱いに注意 |
| `bid_iv` | Bid側IV | 欠損値の扱いに注意 |
| `ask_price` | Ask価格 | 欠損値の扱いに注意 |
| `ask_quantity` | Ask数量 | 欠損値の扱いに注意 |
| `bid_price` | Bid価格 | 欠損値の扱いに注意 |
| `bid_quantity` | Bid数量 | 欠損値の扱いに注意 |
| `iv` | IV | QRI表示値 |
| `change` | 価格変化 | QRI表示値 |
| `change_percent` | 価格変化率 | QRI表示値 |
| `last_price` | 最終約定価格 | 未約定・未取得は空欄になり得る |
| `trade_time` | 最終約定時刻 | 表示形式はQRI側に依存 |

## 2. 差分データ

ファイル：`data/differences.csv`

現行の `get_option_data.py` が生成する差分スナップショットです。主な項目：

- `qri_update_time`、`collected_at`
- `contract`、`option_type`、`strike`
- `previous_open_interest`、`current_open_interest`、`open_interest_diff`
- `previous_volume`、`current_volume`、`volume_diff`
- `previous_last_price`、`current_last_price`、`last_price_diff`
- `previous_ask_quantity`、`current_ask_quantity`、`ask_quantity_diff`
- `previous_bid_quantity`、`current_bid_quantity`、`bid_quantity_diff`
- `alert_type`

差分ファイルは過去の全時点を追記する履歴ではなく、実行時に作り直される最新比較結果です。

## 3. 履歴データ

保存先：`data/history/<限月>/<取引日>.csv`

- 限月ごとのフォルダに分けて保存します。
- ファイル名はQRIの取引日を基準にします。
- 15:45 JST以降に最初に成功した実行のスナップショットを保存します。
- CSVの列構成は最新データと同じ `FIELDNAMES` です。
- `collected_at` と `qri_update_time` で実際の取得時刻を確認できます。

## 4. 独立スクリプト用データ

### `data/previous.csv`

`calculate_difference.py` が `latest.csv` と比較するための前回データです。現行の `get_option_data.py` はこのファイルを比較元として使用しません。

### `data/alert_history.json`

`notify_discord.py` が通知済みキー・時刻などを管理するためのJSONです。ファイル内には旧形式と新形式が混在している可能性があるため、形式を統一する前に移行処理を用意してください。

## 5. 空欄・ゼロの取り扱い（重要）

データ上、次の3状態は区別しなければなりません。

1. **数値0**：データ提供元が明示的に0を示した状態
2. **空欄**：データ提供元が値を表示していない状態
3. **取得失敗・解析失敗**：本来取得すべき値が取得できなかった状態

Pythonの `to_number()` / `number()` とHTMLの `num()` は、空欄・ハイフン等を欠損値として扱います。`open_interest_status` により、QRI原表のハイフンと空セルはCSV上で区別します。数値0は0のまま保持します。差分計算では前回値・今回値の両方が有効な場合だけ差を計算し、どちらかが欠損なら差分も欠損としてCSVへ空欄出力します。

推奨仕様：
- CSVの空欄は空欄のまま保持
- 内部処理では欠損値をNone相当として保持
- 0は数値0として扱う
- 比較元または比較先が欠損なら差分を計算しない
- OIの取得が不完全ならMax Painを計算しない
- 欠損件数・欠損率を画面とログに表示する

## 6. 差分計算のキー

現行の `get_option_data.py` の行照合キーは次の3項目です。

`(contract, option_type, strike)`

出来高差分については、さらに前回・今回の `trading_day` が両方存在し、一致することを確認します。取引日が異なる場合や日付が不明な場合は、出来高差分を空欄にし、出来高アラートを出しません。

OI・価格・板数量の差分は、それぞれ前回・今回の値が有効な数値の場合だけ計算します。OIについては、日次公表値の変化と日中変化を区別するルールが今後の検討課題です。

## 7. HTMLのデータ品質判定とMax Pain

`docs/index.html` は選択中の限月について、CSVの行をStrike単位にまとめ、次を検査します。

- StrikeごとにCALL行・PUT行が各1件あること
- 同じStrike・同じオプション種別の重複行がないこと
- Strike・オプション種別が不正な行がないこと
- CALL OI・PUT OIのすべてが有限の数値であること

CALL/PUTの片側欠損、重複、不正行、OI欠損のいずれかがある場合はMax Pain・OI合計・OI比率を計算・更新しません。画面上部のデータ状態欄にはCALL/PUTペア数、OI取得数・対象数、OI取得率、欠損・重複件数を表示します。

**検出できないケース：** CALLとPUTの両方が同じStrikeで丸ごと欠けている場合、そのStrikeはCSVに現れないため、期待Strike一覧など別の基準データがなければ検知できません。現在はStrikeの連続性・期待範囲を推測で補完しません。

## 8. データの利用上の注意

- QRIの画面表示・配信仕様が変われば、HTML解析が失敗する可能性があります。
- 取得時刻とQRI更新時刻は一致しません。
- 最新CSVは上書きされるため、長期分析にはhistoryを使用してください。
- 履歴はGitリポジトリに蓄積されます。保存期間・ファイルサイズ・リポジトリ容量の上限方針は今後決める必要があります。
- 空欄を0に置き換えた集計や差分は、誤った結論につながる可能性があります。
