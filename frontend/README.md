## Frontend — Next.js

Este frontend consome os endpoints REST do backend FastAPI do projeto `previsao-futebol`.

### Variáveis de ambiente
Veja `.env.example` para um modelo. Nunca coloque segredos aqui!

- `NEXT_PUBLIC_API_URL` — URL base dos endpoints do backend (ex: https://previsao-futebol.onrender.com)
- `NEXT_PUBLIC_CONTENT_VERSION`, `NEXT_PUBLIC_PREDICTIONS_VERSION`, etc — controle de versão de conteúdo/predições

### Desenvolvimento local
```bash
cd frontend
npm ci
npm run dev  # http://localhost:3000
```

### Lint e testes
```bash
npm run lint
npm test --if-present
```

### Build de produção
```bash
npm run build
npm start
```

### Deploy
Recomenda-se usar Vercel, Render ou Docker. Configure as variáveis de ambiente conforme `.env.example`.

---
Este projeto foi iniciado com [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).
