# 日経225オプション需給モニター

QRIが公開する日経225オプション情報を定期取得し、限月・CALL/PUT・Strike別にCSV保存する個人用モニターです。GitHub Actionsでデータ取得を実行し、GitHub Pagesで公開するHTMLから最新CSVを読み込みます。

> **重要：** このREADMEは2026-11-11時点のコードとデータを確認した現状説明です。OI欄のQRIハイフンはJPX日次建玉データ由来の公開表との複数Strike照合に基づき0として集計し、原表状態は `open_interest_status` に保持します。QRI自身の仕様説明は未確認のため、ハイフン件数を画面に残しています。日経平均株価の現在値・QRI表示の約定時刻も取得し、ATMを判定します。

## まず見る場所

- [モニター（GitHub Pages）](https://uro-o.github.io/jpx-option-data-realtime-html/)
- [最新データ](data/latest.csv)
- [GitHub Actions](https://github.com/uro-o/jpx-option-data-realtime-html/actions/workflows/update-option-data.yml)
- [作業手順・運用ガイド](docs/OPERATIONS.md)
- [フォルダ・ファイル一覧](docs/PROJECT_OVERVIEW.md)
- [CSVデータ項目](docs/DATA_DICTIONARY.md)
- [改善課題・優先順位](docs/IMPROVEMENT_BACKLOG.md)

## 現在の処理の流れ

1. GitHub Actionsが5分間隔のスケジュールで起動する（workflowのcronはUTC）。
2. `.github/workflows/update-option-data.yml` がPython 3.12を準備し、`requests` と `beautifulsoup4` をインストールする。
3. `run_option_data.py` が当日基準の3限月とQRI URLを決定する。
4. `run_option_data.py` が `get_option_data.py` の限月設定と履歴保存関数を差し替え、取得処理を実行する。
5. `get_option_data.py` がQRIの3ページを取得・解析し、全限月・全StrikeのCALL/PUTペアを検証する。検証成功後に差分・Discord通知・最新CSV等を更新する。
6. Actionsが `data/` の変更をコミットしてmainへpushする。
7. `docs/index.html` がGitHub上の `data/latest.csv` を読み込み、日経平均株価・QRI約定時刻・ATM・Max Pain・Strike別CALL/PUT情報を表示する。

詳細は[運用ガイド](docs/OPERATIONS.md)を参照してください。

## 主要ファイル

| パス | 役割 |
|---|---|
| `.github/workflows/update-option-data.yml` | 自動実行・依存関係インストール・データcommit |
| `run_option_data.py` | 限月とQRI URLの選定、日次履歴保存の制御 |
| `get_option_data.py` | QRI取得、HTML解析、日経平均株価と時刻の取得、CSV保存、差分計算、Discord通知 |
| `calculate_difference.py` | `latest.csv` と `previous.csv` を比較する独立した差分・通知処理 |
| `detect_large_trades.py` | `differences.csv` を使う独立した大口変動検出処理 |
| `notify_discord.py` | `differences.csv` を使う独立した通知・重複通知管理処理 |
| `docs/index.html` | GitHub Pages用のモニター画面。日経平均株価を基準にATMを緑色表示し、Max Painをオレンジ色表示 |
| `tests/test_data_validation.py` | Python取得検証とHTML側Max Pain品質判定のテスト |
| `data/latest.csv` | 最新取得データ |
| `data/differences.csv` | 現行取得処理が生成する前回比較データ |
| `data/history/` | 限月・取引日別の履歴CSVと保存済みマーカー |
| `data/previous.csv` | 独立差分スクリプトが参照する比較用データ |
| `data/alert_history.json` | 独立通知スクリプトの通知済み管理ファイル |

各ファイルの詳細と注意点は[フォルダ・ファイル一覧](docs/PROJECT_OVERVIEW.md)に記載しています。

## データ取得対象

`run_option_data.py` はQRIの次の3ページを使用します。

| 役割 | URL |
|---|---|
| 先限月 | https://svc.qri.jp/jpx/nkopm/ |
| 2番目の限月 | https://svc.qri.jp/jpx/nkopm/1 |
| 3番目の限月 | https://svc.qri.jp/jpx/nkopm/2 |

限月は固定値ではなく、実行日とSQ日をもとに計算します。2026-11-05に、12月限が2番目と3番目に重複してしまう不具合を修正しました。現在は3番目を「2番目の限月より後にある最初の四半期限月」として選択し、重複した限月キーが生じた場合はエラーにします。

## 現在値・ATM・Max Pain

- 日経平均株価はQRIページ上部の `#priceInfo` にある「日経平均株価 (日経225)」行から取得します。先物価格はATM判定に使用しません。
- CSVの `underlying_current_price` と `underlying_price_time` に保存します。時刻はQRI表示の月/日・時:分です。
- ATMは選択中限月の全Strikeから、日経平均株価に最も近いStrikeを選びます。表示範囲を絞ってもATM判定対象は全Strikeです。
- ATMは緑色、Max Painはオレンジ色です。同一Strikeに重なった場合は両方のマーカーを表示します。
- 3つの限月ページで現在値と時刻が一致しない場合、または取得できない場合はスナップショットを保存しません。

## Volume・OIバーの共通尺度

- CALL Volume・CALL OI・PUT OI・PUT Volumeの4系列は、選択中の限月に含まれる全Strikeの最大値を共通の基準として横幅を計算します。
- 各バーの幅は「各項目の値 ÷ 共通最大値」で算出するため、同じ枚数なら4系列で同じ比率・長さになります。
- 尺度の計算は表示範囲の絞り込みより前に行います。「全Strike」「中央±5,000」「中央±2,500」を切り替えても、同じ値のバー幅は変わりません。
- これは限月内の相対比較用の表示です。限月を切り替えた場合は、その限月の全Strikeを基準に再計算します。

## 実行・更新

- 定期実行：GitHub Actionsのcron `*/5 * * * 1-5`（UTC）
- 手動実行：Actionsの「Update JPX Option Data」から `Run workflow`
- コード変更による自動実行：`.github/workflows/update-option-data.yml`、`run_option_data.py`、`get_option_data.py`、`tests/**` の変更がpushトリガー対象
- HTML：GitHub Pagesで `docs/` を公開する構成

GitHub Actionsのscheduleは指定時刻どおりの起動を保証しません。実際のQRI更新時刻と取得時刻はCSVの `qri_update_time` と `collected_at` で確認してください。

## Discord設定

`get_option_data.py` は環境変数 `DISCORD_WEBHOOK_URL` を参照します。Webhook URLをソースコードやREADMEへ直接記載しないでください。GitHub Actionsで利用する場合は、GitHub Secrets等の安全な仕組みで環境変数として渡す設定が必要です。現在のworkflow本文にはSecretsを環境変数へ渡す記述が見当たらないため、通知が必要な場合は設定状況を確認してください。

## 最終約定価格・約定日時の表示

`data/latest.csv` の `last_price` と `trade_time` は、StrikeごとのCALL/PUTそれぞれの最終約定価格と約定日時です。HTMLではCALL Volume欄・PUT Volume欄の下段に「最終価格 · 約定日時」を併記します。これはQRIページ上部の指数・先物等の現在値とは別データです。約定日時が空欄の場合は、存在しない時刻を補完せず、取得できた最終価格だけを表示します。

## 現在確認されている注意点

- 3限月すべての取得成功と、各StrikeのCALL/PUTペアを検証してから出力を更新します。取得失敗・欠損・重複があれば処理をエラー終了し、既存の最新CSV等を保持します。
- OIはQRIの「-」を0として集計し、`open_interest_status=dash` として原表状態を保存します。空セル・解析不能は引き続き欠損扱いです。その他の数値項目では空欄・ハイフン等を欠損値として扱います。
- 出来高差分は前回・今回の取引日が同じ場合だけ計算します。取引日が変わった場合や日付が不明な場合は、出来高差分・出来高アラートを出しません。
- Discord送信失敗後も最新CSVが更新されるため、通知を再送できない可能性があります。
- `calculate_difference.py`、`detect_large_trades.py`、`notify_discord.py` は独立スクリプトであり、現在のActionsワークフローからは呼び出されていません。
- HTML上部の「現在値」欄は、現状は価格取得処理が未接続です。今回追加するCALL/PUTの `last_price`・`trade_time` 表示とは別項目です。
- HTMLではStrikeごとのCALL/PUTペア、重複行、不正行、OI欠損を検査します。QRIハイフンは0として集計し、件数も表示します。実データではOI数値が全Strikeで揃い、Max Pain・OI合計・OI比率を計算できます。空セル・解析不能が出た場合は従来どおり計算を停止します。ただし、CALL/PUT両方の行が同じStrikeで丸ごと欠けた場合は、QRI側の期待Strike一覧がないため検知できません。
- `requirements.txt` はまだありません。データ完全性・欠損値・差分計算の自動テストを `tests/test_data_validation.py` に追加し、Actionsで毎回実行します。

改善の優先順位は[改善課題一覧](docs/IMPROVEMENT_BACKLOG.md)を参照してください。

## 仕様変更時のルール

1. 変更前に対象ファイルと呼び出し元を確認する。
2. CSVの列名・意味・保存先を変える場合は、このREADMEと `docs/DATA_DICTIONARY.md` も同時に更新する。
3. 限月選定ロジックを変える場合は、年末年始・SQ前後・四半期月のテストを追加する。
4. データ取得ロジックを変える場合は、欠損・空欄・重複・取得失敗のテストを行う。
5. Actions実行結果と生成CSVの件数・限月・CALL/PUT・Strike範囲を確認する。
6. HTMLの表示だけでなく、元CSVの値と一致することを確認する。
7. 作業後は変更日、変更内容、確認結果、未解決事項を文書に残す。

## ドキュメント更新履歴

- 2026-11-05：コードとデータ構成を確認し、READMEおよび運用・構成・データ項目・改善課題の文書を追加。Max PainのCALL/PUTペア・重複・OI取得率チェックとHTMLテストを追加。


- 2026-11-11：HTMLのCALL/PUT各出来高欄に、CSVの `last_price`（最終約定価格）と `trade_time`（最終約定日時）を表示する機能を追加。指数等の現在値欄とは区別。\n- 2026-11-11：CALL/PUTのVolume欄を、最終約定価格とASK/BID価格の一致で方向推定して色分け。ASK一致=赤系、BID一致=青系、判定困難=グレー。累積出来高全体の方向を断定しない旨を仕様書に明記。
- 2026-11-11：CALL Volume・CALL OI・PUT OI・PUT Volumeのバー幅を限月内全Strike共通の最大値で正規化。表示範囲を切り替えても同じ値のバー幅が変わらないよう修正。GitHub Pagesのビルド成功を確認。
