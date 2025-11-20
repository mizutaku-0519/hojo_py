# Jグランツ補助金検索UI - デプロイガイド

このドキュメントでは、Streamlitアプリをウェブ上にデプロイする方法を説明します。

## 対応デプロイ先

- **Streamlit Cloud** (推奨) - 無料、簡単
- **Heroku**
- **Google Cloud Run**
- **AWS EC2/ECS**

## Streamlit Cloudへのデプロイ（推奨）

### 前提条件

1. GitHubアカウント
2. このリポジトリをGitHubにプッシュ済み

### 手順

1. **Streamlit Cloudにアクセス**
   - https://streamlit.io/cloud にアクセス
   - GitHubアカウントでサインイン

2. **新しいアプリをデプロイ**
   - 「New app」ボタンをクリック
   - リポジトリを選択: `your-username/jgrants-mcp-server`
   - ブランチ: `main` (または使用しているブランチ)
   - メインファイルパス: `app.py`
   - 「Deploy」をクリック

3. **デプロイ完了**
   - 数分でアプリがデプロイされます
   - `https://your-app-name.streamlit.app` のようなURLが発行されます

## ローカルでのテスト

デプロイ前に、ローカル環境でテストすることを推奨します：

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# アプリを起動
streamlit run app.py
```

ブラウザで `http://localhost:8501` を開き、以下を確認：

- ✅ 補助金検索が動作する
- ✅ 検索結果が表示される
- ✅ 詳細表示が動作する
- ✅ エラーが発生しない

## デバッグモード

アプリにデバッグモードがあります：

1. サイドバーの「🔧 デバッグモード」をチェック
2. API呼び出しの詳細情報が表示されます
3. エラー発生時の診断に使用

## トラブルシューティング

### エラー: JグランツAPIに接続できません

**原因**: ネットワーク接続、タイムアウト、またはAPIサーバーの問題

**対処法**:
1. デバッグモードを有効にして詳細を確認
2. インターネット接続を確認
3. 時間をおいて再試行

### エラー: HTTPエラー 400

**原因**: 検索パラメータが不正

**対処法**:
1. キーワードが2文字以上であることを確認
2. 特殊文字を使用していないか確認

### エラー: HTTPエラー 500

**原因**: JグランツAPIサーバー側の問題

**対処法**:
1. 時間をおいて再試行
2. JグランツAPIの稼働状況を確認

## 環境変数（オプション）

必要に応じて以下の環境変数を設定できます：

### Streamlit Cloudの場合

1. アプリの設定画面を開く
2. 「Secrets」セクションに移動
3. 以下の形式で追加：

```toml
# 現在は環境変数不要ですが、将来的に追加する場合の例
[api]
timeout = 60
max_retries = 3
```

## ファイル構成

```
jgrants-mcp-server/
├── app.py                  # メインアプリケーション
├── requirements.txt        # Python依存パッケージ
├── .streamlit/
│   └── config.toml        # Streamlit設定
├── README.md              # プロジェクト説明
└── README_DEPLOY.md       # このファイル
```

## パフォーマンス最適化

### キャッシュの活用

将来的にキャッシュ機能を追加することで、パフォーマンスを向上できます：

```python
@st.cache_data(ttl=3600)  # 1時間キャッシュ
def cached_search(keyword):
    return call_jgrants_api("/subsidies", {"keyword": keyword})
```

### タイムアウトの調整

ネットワーク環境に応じてタイムアウトを調整：

```python
# app.py の call_jgrants_api 関数内
timeout=60.0  # デフォルト60秒
```

## セキュリティ

### SSL証明書検証

現在、企業プロキシ対応のため`verify=False`にしていますが、本番環境では以下を推奨：

```python
verify=True  # SSL証明書を検証
```

### CORS設定

`.streamlit/config.toml`で適切なCORS設定を確認してください。

## サポート

問題が発生した場合：

1. デバッグモードを有効にして詳細を確認
2. GitHubのIssuesに報告
3. JグランツAPI公式ドキュメントを確認: https://developers.digital.go.jp/documents/jgrants/api/

## ライセンス

MIT License
