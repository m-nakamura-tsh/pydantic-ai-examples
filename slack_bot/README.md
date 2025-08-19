# Slack Bot Application

ProcessPoolExecutorを使用したバックグラウンドタスク実行とユーザー確認機能を持つSlack Botアプリケーション。

## 機能

- Slackチャンネルでbotにメンション（`@bot run_task`）することでタスクを実行
- バックグラウンドでタスクを実行（ProcessPoolExecutor使用）
- タスク実行中にユーザーへの確認を求める機能
- 承認/拒否ボタンによるインタラクティブな操作
- 拒否時の理由入力フォーム
- SQLiteデータベースによるタスク状態管理

## セットアップ

### 1. 依存関係のインストール

```bash
uv sync
```

### 2. Slack Appの作成

1. [Slack API](https://api.slack.com/apps)にアクセス
2. "Create New App" → "From scratch"を選択
3. App名とワークスペースを設定

### 3. OAuth & Permissions

Bot Token Scopesに以下を追加：
- `app_mentions:read` - メンションを読み取る
- `chat:write` - メッセージを送信
- `channels:history` - チャンネルの履歴を読む
- `groups:history` - プライベートチャンネルの履歴を読む
- `im:history` - ダイレクトメッセージの履歴を読む
- `mpim:history` - グループダイレクトメッセージの履歴を読む

"Install to Workspace"をクリックして、Bot User OAuth Tokenを取得。

### 4. Socket Mode

1. Settings → Socket Modeで有効化
2. App-Level Tokenを生成（connections:write スコープ付き）

### 5. Event Subscriptions

Subscribe to bot eventsに以下を追加：
- `app_mention` - botがメンションされた時

### 6. Interactivity & Shortcuts

- Interactivityを有効化
- Request URLは設定不要（Socket Mode使用のため）

### 7. 環境変数の設定

```bash
export SLACK_APP_TOKEN="xapp-1-..."  # Socket Mode用のApp-Level Token
export SLACK_BOT_TOKEN="xoxb-..."    # Bot User OAuth Token
```

または`.env`ファイルを作成：

```
SLACK_APP_TOKEN=xapp-1-...
SLACK_BOT_TOKEN=xoxb-...
```

## 実行方法

### アプリケーションの起動

```bash
python -m slack_bot.app
```

### テストの実行

```bash
pytest tests/
```

## 使用方法

1. Slackのチャンネルにbotを招待
2. `@bot run_task`とメンションしてタスクを実行
3. タスク実行中に確認メッセージが表示されたら、「承認」または「拒否」ボタンをクリック
4. 拒否の場合は理由を入力

## アーキテクチャ

### ファイル構成

```
slack_bot/
├── __init__.py
├── app.py              # メインのSlack Botアプリケーション
├── background_task.py  # バックグラウンドタスク処理
├── models.py          # SQLAlchemyモデル定義
└── README.md          # このファイル

tests/
├── __init__.py
├── test_slack_bot_app.py           # アプリケーションのテスト
├── test_slack_bot_background_task.py  # バックグラウンドタスクのテスト
└── test_slack_bot_models.py        # データベースモデルのテスト
```

### 主要コンポーネント

- **SlackBot**: メインのボットクラス。イベントハンドラーとアクション処理を管理
- **TaskManager**: ProcessPoolExecutorを使用したタスク実行管理
- **Task**: SQLAlchemyモデル。タスクの状態とメタデータを保存

### データベーススキーマ

| カラム | 型 | 説明 |
|--------|-----|------|
| task_id | String | タスクの一意識別子（UUID） |
| channel_id | String | Slackチャンネル ID |
| thread_ts | String | スレッドのタイムスタンプ |
| user_id | String | タスクを開始したユーザーID |
| status | Enum | タスクのステータス |
| rejection_reason | String | 拒否理由（拒否時のみ） |
| created_at | DateTime | 作成日時 |
| updated_at | DateTime | 更新日時 |

### タスクステータス

- `PENDING`: タスク開始待ち
- `AWAITING_CONFIRMATION`: ユーザー確認待ち
- `APPROVED`: 承認済み
- `REJECTED`: 拒否済み
- `COMPLETED`: 完了

## 開発メモ

- Socket Modeを使用しているため、外部公開URLは不要
- ProcessPoolExecutorは最大4ワーカーで設定
- ダミータスクは単純なsleep処理（本番環境では実際の処理に置き換える）
- データベースはSQLite（本番環境ではPostgreSQL等を推奨）