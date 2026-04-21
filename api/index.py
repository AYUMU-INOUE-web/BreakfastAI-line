"""Vercel Serverless 関数エントリポイント。

@vercel/python ランタイムは WSGI アプリを `app` という名前で export すると
そのまま全リクエストを処理する。ローカル開発や GitHub Actions では
`main.py serve` を使うので、このファイルは Vercel 専用。
"""
from app.admin import create_app

app = create_app()
