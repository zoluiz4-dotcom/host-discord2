# Bot Panel — Backend

API em FastAPI responsável por tudo que precisa acessar o sistema de arquivos
ou controlar processos: criar/iniciar/parar bots, editar arquivos, ler `.env`,
monitorar CPU/RAM, e transmitir logs em tempo real via WebSocket.

O frontend (hospedado no Netlify) fala com esta API por HTTP/WebSocket.

## Deploy no Render (recomendado)

### Antes de tudo: entenda a limitação de disco

O plano padrão do Render (Web Service sem "Persistent Disk") usa **disco
efêmero**: tudo que for gravado em `BOTS_DIR` (código dos bots, `.env` de
cada bot, logs) e o banco `panel.db` (SQLite) **são apagados a cada novo
deploy ou reinício do serviço**. Isso não é um bug deste projeto — é como
o Render funciona por padrão.

Duas formas de resolver, dependendo do que você precisa:

1. **Persistent Disk** (pago, a partir de ~US$1/mês por GB): no painel do
   serviço, em "Disks", adicione um disco e monte em `/app/bots_data`.
   Isso preserva o código dos bots e logs entre deploys. Para o banco de
   dados, aponte `DATABASE_URL` para um arquivo dentro desse mesmo disco.
2. **Banco de dados gerenciado**: crie um banco PostgreSQL no Render (tem
   plano gratuito) e configure `DATABASE_URL` com a "Internal Database
   URL" fornecida. Isso resolve a persistência dos *registros* dos bots,
   mas o *código* de cada bot (arquivos) ainda precisaria do Persistent
   Disk acima para sobreviver a um deploy.

Se seu uso é mais experimental/teste, pode ignorar isso por enquanto e
simplesmente recriar os bots depois de cada deploy.

### Passo a passo (via painel, sem Blueprint)

1. Suba este projeto para um repositório no GitHub (pode conter tanto
   `backend/` quanto `frontend/` no mesmo repo).
2. No [Render](https://dashboard.render.com), clique em **New +** → **Web Service**.
3. Conecte o repositório.
4. Configure:
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Em **Environment**, adicione as variáveis (veja `.env.example` para a
   lista completa; no mínimo, defina `PANEL_API_KEY` e `ALLOWED_ORIGINS`).
   Não defina `PORT` manualmente — o Render já injeta essa variável.
6. Clique em **Create Web Service**. O arquivo `runtime.txt` já fixa a
   versão do Python em `3.12.10`, então o Render não vai tentar usar uma
   versão mais nova por padrão.
7. Quando o deploy terminar, você recebe uma URL tipo
   `https://bot-panel-backend.onrender.com`. Use essa URL na configuração
   do frontend (tela de conexão do painel).
8. Volte em `ALLOWED_ORIGINS` e ajuste para a URL definitiva do seu site
   no Netlify, depois salve — o Render reinicia o serviço automaticamente.

### Passo a passo (via Blueprint, mais rápido)

Este projeto já inclui um `render.yaml`. Se preferir:

1. No Render, clique em **New +** → **Blueprint**.
2. Selecione o repositório. O Render lê `backend/render.yaml` automaticamente.
3. Ele vai pedir para você preencher `PANEL_API_KEY` e `ALLOWED_ORIGINS`
   (marcados como `sync: false` no blueprint, ou seja, você define o valor
   manualmente em vez de vir do arquivo).
4. Confirme e aguarde o deploy.

### Erros comuns no Render e como evitá-los

- **"Application failed to respond" / porta errada:** confira que o Start
  Command usa `$PORT` (variável), nunca um número fixo como `8000`. Já
  está assim no `render.yaml` e nas instruções acima.
- **Build falha ao instalar dependências:** confirme que o `Root Directory`
  está configurado como `backend` — se o Render tentar instalar a partir
  da raiz do repositório (onde também existe `frontend/`), ele não vai
  encontrar o `requirements.txt` no lugar esperado.
- **CORS bloqueando o frontend:** confira `ALLOWED_ORIGINS` — precisa ser
  exatamente a URL do seu site Netlify, incluindo `https://` e sem barra
  no final.
- **Bots "desaparecem" depois de um deploy:** é o disco efêmero (veja
  seção acima). Não é erro de configuração, é o comportamento padrão do
  Render sem Persistent Disk.

## Instalação em VPS própria (alternativa ao Render)

```bash
# 1. Copie a pasta backend/ para a VPS
scp -r backend usuario@SEU_IP:/home/usuario/botpanel-backend

# 2. Entre na VPS
ssh usuario@SEU_IP
cd botpanel-backend

# 3. Configure as variáveis de ambiente
cp .env.example .env
nano .env
# -> defina PANEL_API_KEY com uma chave forte (ex: openssl rand -hex 32)
# -> defina ALLOWED_ORIGINS com a URL do seu site no Netlify

# 4. Suba com Docker Compose (recomendado; docker-compose.yml é só para VPS,
#    o Render não usa esse arquivo)
docker compose up -d --build

# Ou, sem Docker, direto com Python:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Numa VPS própria, ao contrário do Render, o disco é permanente por padrão
— não há a limitação de disco efêmero descrita acima, e `USE_DOCKER=true`
funciona normalmente (o Render não dá acesso ao socket Docker do host,
então essa opção só é válida em VPS própria).

## HTTPS (necessário tanto no Render quanto na VPS)

O navegador bloqueia chamadas de um site HTTPS (Netlify) para uma API HTTP
simples. No Render, isso já vem resolvido automaticamente — todo serviço
web recebe HTTPS por padrão, sem configuração extra.

Numa VPS própria, você precisa configurar isso manualmente, por exemplo
com Caddy:

```bash
sudo apt install -y caddy
```

`Caddyfile`:
```
api.seudominio.com {
    reverse_proxy localhost:8000
}
```

Se você ainda não tem domínio, pode usar HTTPS com certificado autoassinado
ou serviços como Cloudflare Tunnel, que dão HTTPS sem precisar de domínio
próprio configurado manualmente.

## Autostart no boot do servidor

No Render, o serviço reinicia automaticamente em caso de falha ou deploy —
isso já cobre o "iniciar automaticamente com o servidor". Numa VPS com
Docker Compose, o `restart: unless-stopped` cumpre o mesmo papel. Em ambos
os casos, os bots marcados com "Iniciar automaticamente com o servidor" são
iniciados pelo próprio backend assim que ele sobe (veja `app/main.py`).

## Estrutura

```
backend/
  runtime.txt       # fixa a versão do Python (3.12.10) para o Render
  render.yaml        # blueprint de deploy automatizado no Render
  requirements.txt   # dependências Python
  Dockerfile          # alternativa a runtime nativo, também usável no Render
  docker-compose.yml  # uso exclusivo de VPS própria (Render não usa)
  app/
    core/       # configuração, segurança (chave de API), banco de dados
    models/     # modelos SQLAlchemy e schemas Pydantic
    routers/    # rotas da API (bots, arquivos, env, monitoramento, console)
    services/   # lógica de negócio (processos, arquivos, docker, stats)
  bots_data/    # onde o código de cada bot fica salvo (criado automaticamente)
```

