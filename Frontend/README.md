# Frontend — локальная разработка

Требуется Node.js 20+. Сначала запустите Backend на `http://localhost:8000` (см. [Backend/README.md](../Backend/README.md)). Из корня репозитория:

```bash
cd Frontend
npm ci
npm run dev
```

Откройте http://localhost:5173. Vite проксирует `/api` на Backend. Для другого адреса API задайте переменную окружения `API_TARGET` при запуске Vite.

Сборка и тесты из `Frontend/`:

```bash
npm run build
node --test
```
