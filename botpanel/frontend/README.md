# Bot Panel — Frontend

Interface estática (HTML/CSS/JS puro, sem build) do painel de hospedagem de
bots. Feita para deploy direto no Netlify, sem etapa de build.

## Arquivos

```
frontend/
  index.html      # estrutura da aplicação
  styles.css      # design system (cores, tipografia, componentes base)
  views.css       # estilos específicos de cada tela
  api.js          # cliente HTTP (injeta a chave de API automaticamente)
  app.js          # toda a lógica da aplicação
  config.js       # URL padrão do backend (opcional, pode configurar no app)
  netlify.toml    # configuração de deploy e headers de segurança
```

## Deploy no Netlify

**Opção A — Arrastar e soltar:**
1. Acesse [app.netlify.com/drop](https://app.netlify.com/drop).
2. Arraste a pasta `frontend/` inteira.
3. Pronto — você recebe uma URL tipo `https://algo-aleatorio.netlify.app`.

**Opção B — Via Git (recomendado para atualizações futuras):**
1. Suba a pasta `frontend/` para um repositório Git (GitHub, GitLab, etc).
2. No Netlify, clique em "Add new site" → "Import an existing project".
3. Selecione o repositório. Configuração de build:
   - **Build command:** (deixe vazio)
   - **Publish directory:** `.` (ou o caminho até a pasta `frontend`, se o
     repositório tiver outras pastas como `backend/`)

## Primeira configuração

Depois do deploy, abra o site publicado. Na primeira vez, ele vai pedir:
- **URL do backend** — o endereço da sua API (ex: `https://api.seudominio.com`).
- **Chave de API** — a mesma que você definiu em `PANEL_API_KEY` no `.env`
  do backend.

Essas informações ficam salvas apenas no `localStorage` do seu navegador.
Não é uma tela de login: você não vê isso de novo depois da primeira vez,
a menos que troque de navegador ou limpe os dados do site.

## Importante: CORS

O backend só aceita requisições vindas das origens listadas em
`ALLOWED_ORIGINS` (no `.env` do backend). Depois de saber a URL definitiva
do seu site no Netlify, adicione-a lá, por exemplo:

```
ALLOWED_ORIGINS=https://seu-painel.netlify.app
```
