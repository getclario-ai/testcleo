# Use Node.js to build the React app
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Accept build argument for API URL (defaults to localhost for local dev)
ARG REACT_APP_API_BASE_URL=http://localhost:8000
ENV REACT_APP_API_BASE_URL=$REACT_APP_API_BASE_URL

# Build the app
RUN npm run build

# Use nginx to serve the built app
FROM nginx:alpine

# Copy built files to nginx
COPY --from=builder /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create startup script that replaces PORT in nginx config and starts nginx
RUN echo '#!/bin/sh' > /start-nginx.sh && \
    echo 'PORT=${PORT:-8080}' >> /start-nginx.sh && \
    echo 'sed -i "s/listen \${PORT:-8080};/listen $PORT;/" /etc/nginx/conf.d/default.conf' >> /start-nginx.sh && \
    echo 'exec nginx -g "daemon off;"' >> /start-nginx.sh && \
    chmod +x /start-nginx.sh

# Expose port
EXPOSE 8080

# Start nginx
CMD ["/start-nginx.sh"]

