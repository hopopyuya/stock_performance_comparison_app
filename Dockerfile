# ベースイメージとして公式のPythonイメージを使用
FROM python:3.9-slim

# 必要なシステムパッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    vim \
    supervisor \
    curl \
    tar \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを設定
WORKDIR /app

# Pythonパッケージのインストール
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Supervisorの設定ファイルをコピー
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# アプリケーションファイルをコピー
COPY workspace/ /app/workspace/

# エントリポイントスクリプトをコピー
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ポートの開放
EXPOSE 80 8888

# エントリポイントスクリプトを起動
CMD ["/app/entrypoint.sh"]
