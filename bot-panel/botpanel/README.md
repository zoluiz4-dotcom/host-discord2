# Bot Panel

Painel de hospedagem e gerenciamento de bots, com editor de código integrado,
gerenciador de arquivos, variáveis de ambiente, console em tempo real e
monitoramento de recursos.

## Arquitetura

```
┌─────────────────────┐         HTTPS/WSS          ┌──────────────────────┐
│   Frontend (Netlify) │ ───────────────────────────▶│  Backend (sua VPS)   │
│   HTML/CSS/JS puro   │  header X-API-Key           │  FastAPI + SQLite    │
│   sem build step     │  em toda requisição          │  processos dos bots │
└─────────────────────┘                              └──────────────────────┘
```

- **Frontend**: site estático, publicado no Netlify. Não tem acesso direto
  ao sistema de arquivos ou processos — só conversa com o backend por HTTP
  e WebSocket.
- **Backend**: API em FastAPI que roda na sua VPS. É quem de fato inicia
  bots, lê/escreve arquivos, lê `.env`, mede CPU/RAM, etc.

Essa separação existe porque o Netlify só hospeda arquivos estáticos — ele
não pode executar processos de longa duração (seus bots) nem acessar um
sistema de arquivos persistente. Por isso qualquer coisa que precise
"tocar o sistema" mora no backend, na VPS.

## Segurança: por que existe uma chave de API

Você pediu um painel sem tela de login — e é isso que foi entregue: nenhum
formulário de usuário/senha, nenhuma sessão, nenhum cadastro. Mas o
frontend fica public no Netlify, e o endereço do seu backend aparece no
código do navegador para qualquer visitante do site. Sem alguma trava, um
scanner automático da internet eventualmente encontraria o endereço do seu
backend e conseguiria iniciar/parar/excluir bots e ler seus `.env` sem
nenhuma barreira.

A solução foi uma chave de API (`PANEL_API_KEY`) que:
- é digitada **uma única vez**, na primeira vez que você abre o site;
- fica salva no `localStorage` do seu navegador;
- é enviada automaticamente em toda chamada ao backend depois disso.

Você nunca vê uma tela de login no seu uso normal — só na primeira vez, e
nem é chamada de "login" na interface, é "conectar ao servidor".

## Como colocar no ar

### 1. Backend (VPS)

Veja `backend/README.md` para o passo a passo completo. Resumo:

```bash
scp -r backend usuario@SEU_IP:/home/usuario/botpanel-backend
ssh usuario@SEU_IP
cd botpanel-backend
cp .env.example .env
nano .env   # defina PANEL_API_KEY e ALLOWED_ORIGINS
docker compose up -d --build
```

Configure HTTPS na frente da API (Caddy, Nginx + Let's Encrypt, ou
Cloudflare Tunnel) — navegadores bloqueiam chamadas de um site HTTPS para
uma API HTTP simples.

### 2. Frontend (Netlify)

Veja `frontend/README.md`. Resumo:

1. Arraste a pasta `frontend/` para [app.netlify.com/drop](https://app.netlify.com/drop), ou conecte via Git.
2. Abra o site publicado, informe a URL do backend e a chave de API.
3. Depois, volte no `.env` do backend e ajuste `ALLOWED_ORIGINS` para a URL
   definitiva que o Netlify te deu.

## Funcionalidades incluídas

- Dashboard com CPU/RAM/disco do servidor, bots online/offline, uptime.
- CRUD completo de bots: criar, iniciar, parar, reiniciar, excluir.
- Reinício automático em caso de crash (configurável por bot).
- Inicialização automática dos bots quando o servidor reinicia.
- Editor de código no navegador (CodeMirror): múltiplas abas, destaque de
  sintaxe, autocompletar de parênteses/aspas, busca, atalhos tipo VS Code
  (Ctrl+S para salvar).
- Gerenciador de arquivos: upload, download, upload de ZIP com extração,
  criar/renomear/excluir/copiar/mover arquivos e pastas.
- Variáveis de ambiente (`.env`) por bot, com valores ocultos por padrão.
- Console em tempo real via WebSocket, com histórico, busca e download.
- Isolamento opcional via Docker por bot (`USE_DOCKER=true` no backend).

## Limitações conhecidas / próximos passos

- O isolamento via Docker (`docker_service.py`) está implementado mas não
  conectado ao fluxo principal de start/stop — hoje os bots rodam como
  subprocessos do próprio backend. Se o isolamento total por container for
  essencial para você, é o próximo passo natural de evolução.
- Autocompletar de código é o básico do CodeMirror (fechamento de
  parênteses/aspas); não há IntelliSense completo como no VS Code.
- Não há backup automático agendado ainda — hoje a proteção é manual via
  download de ZIP; ficaria fácil de adicionar com um cron job simples.
