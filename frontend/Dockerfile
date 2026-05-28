FROM node:20-alpine AS builder

WORKDIR /app

# Build-time vars for Vite. `VITE_*` names are inlined into the JS bundle
# at `npm run build` time — setting them in the running container has no
# effect, so they must arrive as Docker build args (passed through from
# docker-compose.yml's frontend.build.args). Empty default keeps dev / CI
# builds working without requiring the env var to be set.
ARG VITE_TURNSTILE_SITE_KEY=""
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Copy built application
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules

# Expose port
EXPOSE 3000

# Set environment
ENV NODE_ENV=production
ENV PORT=3000

# Run the application
CMD ["node", "build"]
