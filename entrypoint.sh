#!/bin/bash

# .streamlit ディレクトリを作成
mkdir -p /app/workspace/.streamlit

# GCP サービスアカウントキーを環境変数から取得し、secrets.toml に書き込む
cat <<EOT > /app/workspace/.streamlit/secrets.toml
[gcp_service_account]
type = "service_account"
project_id = "${GCP_PROJECT_ID}"
private_key_id = "${GCP_PRIVATE_KEY_ID}"
private_key = """${GCP_PRIVATE_KEY}"""
client_email = "${GCP_CLIENT_EMAIL}"
client_id = "${GCP_CLIENT_ID}"
auth_uri = "${GCP_AUTH_URI}"
token_uri = "${GCP_TOKEN_URI}"
auth_provider_x509_cert_url = "${GCP_AUTH_PROVIDER_X509_CERT_URL}"
client_x509_cert_url = "${GCP_CLIENT_X509_CERT_URL}"
EOT

# supervisord を起動
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
