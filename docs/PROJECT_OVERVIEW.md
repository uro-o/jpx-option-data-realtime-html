# フォルダ・ファイル構成

最終確認日：2026-11-11

この文書はmainブランチの実ファイルを確認して作成しています。ファイルの追加・削除・役割変更があった場合は更新してください。

## 1. 現在の構成

```text
jpx-option-data-realtime-html/
├── .gitignore
├── .github/
│   └── workflows/
│       └── update-option-data.yml
├── data/
│   ├── latest.csv
│   ├── previous.csv
│   ├── differences.csv
│   ├── alert_history.json
│   └── history/
│       ├── .fixed-1545-YYYY-MM-DD.done
│       └── YYYY-MM/
│           └── YYYY-MM-DD.csv
├── docs/
│   ├── index.html
│   ├── PROJECT_OVERVIEW.md
│   ├── OPERATIONS.md
│   ├── DATA_DICTIONARY.md
│   └── IMPROVEMENT_BACKLOG.md
├── tests/
│   └── test_data_validation.py
├── run_option_data.py
├── get_option_data.py
├── calculate_difference.py
├── detect_large_trades.py
├── notify_discord.py
└── README.md
```

※ `data/history/` 以下には日付別の保存済みマーカーと、限月ごとのサブフォルダがあります。履歴CSVは概ね `data/history/<限月>/<取引日>.csv` の形式です。

## 2. Pythonファイル

### `run_option_data.py` — 実行入口・限月選定

GitHub Actionsから実行される入口です。

主な役割：
- JSTで実行日を取得
- SQ日を基準に先限月を決定
- 2番目の限月を翌月として決定
- 3番目の限月を2番目より後の最初の四半期限月として決定
- QRIの `/`, `/1`, `/2` URLを限月へ割り当て
- 限月キーの重複を検知
- `get_option_data.py` の `CONTRACTS` を実行時に差し替え
- 履歴保存関数を15:45 JST以降の初回成功時に保存する関数へ差し替え
- `get_option_data.main()` を呼び出す

注意：
- ここで `get_option_data.py` の一部設定・関数を上書きするため、2ファイルを別々に変更しないこと。
- 履歴の「15:45」は実行予定時刻ではなく、15:45以降に最初に成功した実行時点を意味します。

### `get_option_data.py` — 現行データ取得・保存の中心

主な役割：
- QRIページのHTTP取得
- BeautifulSoupによるHTML解析
- 限月情報・取引日・SQ日・QRI更新時刻の取得
- CALL/PUTのオプション行の抽出
- 3限月すべての取得完了、各StrikeのCALL/PUTペア、重複行、想定外限月の検証
- 検証成功後にのみ差分・最新CSV・履歴の更新へ進む
- `latest.csv` を一時ファイル経由で安全に置換
- `latest.csv` の読み込みと保存
- 前回取得データとの比較
- `differences.csv` の生成
- Discordアラート候補の作成と送信
- 日次履歴保存関数の呼び出し

現行のActions経路では、実際の取得・差分・通知・最新CSV保存を担当します。

重要な注意：
- 3限月すべての取得成功を必須にしていません。一部の取得例外をログに出して次の限月へ進みます。
- 全限月のうち1つでもレコードがあれば処理が進む可能性があります。
- 数値変換関数は欠損値と数値0を区別します。OIはQRIハイフンを照合に基づき0として扱い、open_interest_status列で原表状態を保持します。
- 行照合キーは限月・CALL/PUT・Strikeです。出来高差分はさらに前回・今回の `trading_day` が一致する場合だけ計算します。
- Discord通知が完了したかどうかと、最新データ保存が連動していません。

### `calculate_difference.py` — 独立した差分・通知プログラム

主な役割：
- `data/latest.csv` と `data/previous.csv` を比較
- 出来高・OI・価格・IVなどの差分を計算
- アラート候補を抽出
- Discord通知
- `previous.csv` を更新

現行の `update-option-data.yml` からは呼び出されていません。単独実行する場合は、`get_option_data.py` の差分処理と二重管理にならないよう注意してください。

### `detect_large_trades.py` — 独立した大口変動検出

主な役割：
- `data/differences.csv` を読み込み
- 大口変動・アラート候補を抽出
- 検出結果を保存
- Discord通知

現行のActions経路からは呼び出されていません。入力CSVがどの処理で生成されたかを確認してから実行してください。

### `notify_discord.py` — 独立したDiscord通知処理

主な役割：
- `data/differences.csv` を読み込み
- 通知条件に該当する行を分析
- `data/alert_history.json` を参照して重複通知を抑制
- Discord送信後に通知済み情報を保存

現行のActions経路からは呼び出されていません。通知履歴の形式も他のスクリプトと統一されているとは限らないため、統合前に整理が必要です。

## 3. HTML

### `docs/index.html`

GitHub Pagesで公開する画面です。

現状の主な機能：
- `data/latest.csv` をraw.githubusercontent.comから取得
- CSVをブラウザ内で解析
- 限月選択
- 全Strike／中央±5,000／中央±2,500の表示切替
- CALL Volume、CALL OI、Strike、PUT OI、PUT Volumeの表示
- CALL/PUTそれぞれの `last_price` と `trade_time` を出来高欄の下段に表示
- Max Painの表示・ブラウザ内保存
- QRI更新時刻とデータ取得時刻の表示
- 60秒間隔の自動再読込（実装上の設定）

注意：
- 上部の現在値表示欄は、現在値を設定する取得処理が未接続です。CALL/PUT別の最終約定価格・約定日時表示とは別項目です。
- JavaScriptの数値変換は欠損値と数値0を区別します。
- OIのQRIハイフンは0として計算し、原表状態はopen_interest_statusに保持します。
- StrikeごとのCALL/PUT行数、重複、不正行、真のOI欠損を検査し、不完全な場合はMax Pain・OI合計・OI比率を無効化します。画面にはCALL/PUTペア数とハイフン件数を表示します。
- 「更新」ボタンはActions workflowへのリンクを開く構造であり、画面内で取得処理を直接実行するものではありません。

## 4. データフォルダ

| ファイル／フォルダ | 内容 | 主な利用者 |
|---|---|---|
| `data/latest.csv` | 最新取得時点の全限月データ | HTML、get_option_data.py、calculate_difference.py |
| `data/previous.csv` | 独立差分処理用の比較元データ | calculate_difference.py |
| `data/differences.csv` | 前回データとの比較結果 | 現行取得処理、独立分析スクリプト |
| `data/alert_history.json` | 通知済みアラートの管理情報 | notify_discord.py |
| `data/history/<限月>/<日付>.csv` | 限月別の日次固定時刻スナップショット | 履歴分析 |
| `data/history/.fixed-1545-<日付>.done` | 固定時刻スナップショット保存済みマーカー | run_option_data.py |

### 保存データの扱い

- `latest.csv` は毎回の正常処理で上書きされる最新データです。
- `differences.csv` は差分結果のスナップショットで、過去の全差分を蓄積する履歴ではありません。
- `history/` は取引日別・限月別のスナップショットです。
- `previous.csv` は現行の取得スクリプトが比較元として直接使用しているファイルではありません。独立した `calculate_difference.py` 用です。
- `alert_history.json` は独立した `notify_discord.py` 用です。

## 5. ワークフロー

### `.github/workflows/update-option-data.yml`

- cron：`*/5 * * * 1-5`（UTC）
- 手動起動：workflow_dispatch
- push起動：workflow自身、`run_option_data.py`、`get_option_data.py`、`tests/**` の変更時
- Python：3.12
- インストール：requests、beautifulsoup4
- 実行：`python run_option_data.py`
- 保存：`git add data/` でデータをコミット・push
- concurrency：同一グループの実行を直列化し、実行中の処理をキャンセルしない設定

注意：
- GitHub ActionsのcronはUTCです。日本時間に換算すると+9時間です。
- `get_option_data.py` とテストファイルの変更でもpushトリガーが起動します。
- workflow本文では `DISCORD_WEBHOOK_URL` を環境変数に渡す設定が確認できていません。
- 実行時間上限（timeout-minutes）は明示されていません。

## 6. 現時点で未整備のもの

- README（本書で追加）
- 詳細な運用手順（本書で追加）
- CSV項目辞書（本書で追加）
- 改善課題一覧（本書で追加）
- requirements.txt
- 自動テスト（Python側の取得検証とNode.jsによるHTML側の品質判定テスト）
- データ品質検査専用モジュール
- 通知キュー／再送管理
- データ保存期間・古い履歴の整理ルール
