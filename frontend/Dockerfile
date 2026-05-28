FROM node:20-alpine

WORKDIR /app

# 依存ライブラリを先にインストール（キャッシュ最適化）
COPY package*.json ./
RUN npm ci

# アプリケーションコードをコピー
COPY . .

EXPOSE 3000

# 本番用ビルドして起動
# 開発時は override.yml で "npm run dev" に上書きされる
RUN npm run build
CMD ["npm", "run", "start"]
