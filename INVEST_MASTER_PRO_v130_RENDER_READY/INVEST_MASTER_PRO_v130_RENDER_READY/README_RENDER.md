# INVEST MASTER PRO v130 RENDER READY

## Render設定

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Runtime: Python 3

## 注意

- 無料プランはスリープすることがあります。
- SQLiteはRenderの無料環境では永続化されない可能性があります。
- 本格運用ではPostgreSQL化推奨。
- 初期ユーザーは既存仕様通り。公開後は必ずパスワード変更/新規ユーザー作成してください。
