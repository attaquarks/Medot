# Node sidecar running Baileys + the REST bridge.
FROM node:20-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json tsconfig.json ./
RUN npm install
COPY src ./src
RUN npm run build

EXPOSE 8085
CMD ["node", "dist/index.js"]
