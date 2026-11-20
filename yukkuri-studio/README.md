# AI Yukkuri Studio

動画とシナリオからゆっくり実況動画を自動生成・編集するWebアプリ。現在は **Phase 1（基礎システム）** まで。

## 起動手順

```bash
# 1. DB (PostgreSQL)
docker compose up -d

# 2. バックエンド (Python 3.11+ / FFmpeg が必要)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # 必要なら編集
uvicorn app.main:app --reload   # http://localhost:8000/docs でAPI確認

# 3. フロントエンド (Node 20+)
cd ../frontend
npm install
npm run dev                     # http://localhost:5173
```

テスト（外部サービス不要、SQLiteで動作）: `cd backend && pytest`
型チェック＋ビルド: `cd frontend && npm run build`

## シナリオの書式
`話者: セリフ`（半角/全角コロン）。話者のない行は直前の話者を引き継ぐ。`#` で始まる行は無視。
同時会話は書式ではなく、画面上でセリフを複数選択して「同時にする」で指定する（`simultaneous_group`）。

## 進捗（Phase 1）

| 機能 | 状態 |
|---|---|
| F-01〜05 プロジェクト作成/一覧/開く/改名/削除 | 実装完了（未テスト実行） |
| F-06〜09 MP4アップロード・ffprobe情報取得・プレビュー・紐づけ | 実装完了（未テスト実行） |
| F-10, 12〜14 シナリオ入力・セリフ追加編集削除・話者指定・複数キャラ | 実装完了（未テスト実行） |
| F-11 ファイル読み込み | 未着手（テキスト入力のみ） |
| F-15 同時会話のデータ構造と設定UI | 実装完了（未テスト実行） |
| F-16〜20 キャラクター登録・外見・性格・話し方・音声設定の保存 | 実装完了（未テスト実行） |
| F-21 表情差分 / 画像管理 | 未着手（Phase 2） |
| DBテーブル定義（assets, timeline_items 等） | 定義のみ。APIは後続Phase |
| Alembicマイグレーション | 未着手（現状は起動時 create_all） |

「テスト完了」はまだありません。書いたテスト（pytest 17件）は未実行です。

## ディレクトリ
`backend/app/{api,schemas,services,storage,core}` / `models.py` / `frontend/src/{api,types,hooks,components,pages,features}`
