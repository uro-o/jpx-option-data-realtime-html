# CSVデータ項目・保存仕様

最終更新日：2026-11-11（日経平均現在値・QRI時刻・ATM表示を追加）

## 1. 最新データ

ファイル：`data/latest.csv`

現行コードの `FIELDNAMES` に基づく列一覧です。`open_interest_status` は2026-11-09追加列です。

| 列名 | 意味 | 注意点 |
|---|---|---|
| `underlying_current_price` | QRI参考価格情報の日経平均株価（Nikkei 225現物指数） | ATM判定の基準。先物価格ではない。全オプション行に同じスナップショット値を保持 |
| `underlying_price_time` | 上記日経平均株価に併記されたQRI時刻 | `M/D HH:MM` 形式。QRI表示どおりの月/日・時:分。取得時刻 `collected_at` とは異なる |
| `qri_update_time` | QRIページの更新時刻 | QRI側の時刻。取得時刻とは異なる |
| `collected_at` | プログラムが取得した日時 | JSTオフセット付きISO形式 |
| `trading_day` | QRIが示す取引日 | 夜間取引では暦日と異なる場合がある |
| `last_trading_day` | 限月の最終取引日 | QRIページから取得 |
| `contract` | 限月（YYYY-MM） | 例：2026-12 |
| `option_type` | CALLまたはPUT | 種別 |
| `strike` | 権利行使価格 | 数値 |
| `settlement` | 清算値 | QRI表示値 |
| `open_interest` | 建玉残高（OI） | QRIの「-」は照合に基づき0として保存。空セルは欠損 |
| `open_interest_status` | OI原表セルの状態 | `numeric` / `dash` / `blank` / `invalid`。原表の表示状態を保持 |
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
| `trade_time` | 当該CALL/PUTの最終約定時刻 | 同じ行の `last_price` に対応。表示形式はQRI側に依存。CALL/PUT別に保持 |

`underlying_current_price` と `underlying_price_time` はページ上部の参考価格情報にある日経平均株価と、その値に併記された時刻です。3限月ページ間で値・時刻が一致することを確認してから保存します。HTMLはこの価格を使い、選択限月の全Strikeのうち最も近いStrikeをATMとします。表示範囲を絞る前に判定するため、画面フィルターによってATMが変わることはありません。

`last_price` と `trade_time` はオプション銘柄ごとの情報です。HTMLではCALL Volume欄・PUT Volume欄の下段に「最終価格 · 約定日時」として表示します。QRIページ上部の指数等の現在値・約定日時とは異なります。

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

## 5. 空欄・ゼロ・QRIハイフンの取り扱い（重要）

データ上、次の状態を区別します。

1. **数値0**：数値として明示された0
2. **QRIハイフン**：原表のセルに「-」が表示される状態。JPX日次建玉データ由来の公開表との複数Strike照合で0表示との整合を確認したため、現在は `open_interest=0` として計算します
3. **空欄**：データ提供元が値を表示していない状態。欠損値として保持します
4. **解析不能**：想定外の文字列等。欠損値として保持します

QRI自身の仕様説明でハイフンの意味を確認できていないため、`open_interest_status` 列に原表状態（`numeric` / `dash` / `blank` / `invalid`）を保存し、ハイフン件数を画面にも表示します。QRIの原表表記を失わずに、現時点の照合結果に基づいて0として集計する設計です。

推奨仕様：
- QRIハイフンはOIに限り0として計算し、status列に `dash` を保持
- 空欄・解析不能はNone相当として保持し、0へ置換しない
- 比較元または比較先が真の欠損なら差分を計算しない
- 空欄・解析不能が1件でもある場合はMax Pain・OI合計・OI比率を計算しない
- OI原表状態別の件数をログと画面で確認する

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
