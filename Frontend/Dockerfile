FROM node:22-alpine
WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci
COPY --chown=node:node index.html vite.config.js ./
COPY --chown=node:node src ./src
RUN npm run build

EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
