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

# ngrokのインストール (v3)
RUN wget https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-v3-stable-linux-amd64.tgz && \
    tar -xvzf ngrok-v3-stable-linux-amd64.tgz && \
    mv ngrok /usr/local/bin/ && \
    chmod +x /usr/local/bin/ngrok && \
    rm ngrok-v3-stable-linux-amd64.tgz

# 作業ディレクトリを設定
WORKDIR /app

# Pythonパッケージのインストール
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Supervisorの設定ファイルをコピー
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# アプリケーションファイルをコピー
COPY workspace/ /app/workspace/

# 作業ディレクトリを変更
WORKDIR /app/workspace

# ポートの開放
EXPOSE 80 4040 8888

# Supervisorを起動
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
