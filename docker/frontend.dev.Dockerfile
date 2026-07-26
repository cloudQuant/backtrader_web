# Development Dockerfile for Frontend (Vite dev server with HMR)
FROM node:20-alpine

WORKDIR /app

# Install dependencies first for better layer caching
COPY src/frontend/package*.json ./

RUN npm ci

# Source code will be mounted as a volume for hot-reload
# Copy only as fallback if volume mount is not configured
COPY src/frontend/ ./

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
