FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps
ENV NEXT_PUBLIC_API_URL=/api/v1
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
