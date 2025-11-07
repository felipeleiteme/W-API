FROM node:18-slim

WORKDIR /app

COPY package.json ./
RUN npm install --production && npm cache clean --force

COPY index.js ./

EXPOSE 3000

CMD ["npm", "start"]
