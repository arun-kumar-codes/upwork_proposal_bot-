FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY index.js ./
ENV NODE_ENV=production
EXPOSE 9000
CMD ["node", "index.js"]
