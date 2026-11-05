# 日経225オプション需給モニター

QRIが公開する日経225オプション情報を定期取得し、限月・CALL/PUT・Strike別にCSV保存する個人用モニターです。GitHub Actionsでデータ取得を実行し、GitHub Pagesで公開するHTMLから最新CSVを読み込みます。

> **重要：** このREADMEは2026-11-05時点のコードとリポジトリ構成を確認して作成した現状説明です。実装済みの機能と、今後の改善予定を区別しています。記載した注意事項が解消されるまでは、データ欠損や差分・通知の誤判定が起こり得るため、売買判断の唯一の根拠にしないでください。

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
7. `docs/index.html` がGitHub上の `data/latest.csv` を読み込み、Strike別のCALL/PUT情報を表示する。

詳細は[運用ガイド](docs/OPERATIONS.md)を参照してください。

## 主要ファイル

| パス | 役割 |
|---|---|
| `.github/workflows/update-option-data.yml` | 自動実行・依存関係インストール・データcommit |
| `run_option_data.py` | 限月とQRI URLの選定、日次履歴保存の制御 |
| `get_option_data.py` | QRI取得、HTML解析、CSV保存、差分計算、Discord通知 |
| `calculate_difference.py` | `latest.csv` と `previous.csv` を比較する独立した差分・通知処理 |
| `detect_large_trades.py` | `differences.csv` を使う独立した大口変動検出処理 |
| `notify_discord.py` | `differences.csv` を使う独立した通知・重複通知管理処理 |
| `docs/index.html` | GitHub Pages用のモニター画面 |
| `tests/test_data_validation.py` | 3限月の完全性・重複・CALL/PUTペア検証テスト |
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

## 実行・更新

- 定期実行：GitHub Actionsのcron `*/5 * * * 1-5`（UTC）
- 手動実行：Actionsの「Update JPX Option Data」から `Run workflow`
- コード変更による自動実行：現状は `run_option_data.py` の変更のみがpushトリガー対象
- HTML：GitHub Pagesで `docs/` を公開する構成

GitHub Actionsのscheduleは指定時刻どおりの起動を保証しません。実際のQRI更新時刻と取得時刻はCSVの `qri_update_time` と `collected_at` で確認してください。

## Discord設定

`get_option_data.py` は環境変数 `DISCORD_WEBHOOK_URL` を参照します。Webhook URLをソースコードやREADMEへ直接記載しないでください。GitHub Actionsで利用する場合は、GitHub Secrets等の安全な仕組みで環境変数として渡す設定が必要です。現在のworkflow本文にはSecretsを環境変数へ渡す記述が見当たらないため、通知が必要な場合は設定状況を確認してください。

## 現在確認されている注意点

- 3限月すべての取得成功と、各StrikeのCALL/PUTペアを検証してから出力を更新します。取得失敗・欠損・重複があれば処理をエラー終了し、既存の最新CSV等を保持します。
- Pythonの数値変換とHTML表示で、空欄・ハイフン等を欠損値として扱い、数値0と区別します。差分は前回・今回の両方が有効な数値の場合だけ計算します。
- 差分キーに取引日が含まれず、取引日切替時の出来高差分に注意が必要です。
- Discord送信失敗後も最新CSVが更新されるため、通知を再送できない可能性があります。
- `calculate_difference.py`、`detect_large_trades.py`、`notify_discord.py` は独立スクリプトであり、現在のActionsワークフローからは呼び出されていません。
- HTMLの現在値欄には現状、価格を設定する取得処理がありません。
- HTMLでは欠損値を「—」で表示し、欠損OIが1つでもある限月ではMax Pain・OI合計・OI比率を計算しません。Strike全体の欠落検知は今後の改善課題です。
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

- 2026-11-05：コードとデータ構成を確認し、READMEおよび運用・構成・データ項目・改善課題の文書を追加。
