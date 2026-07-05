# Bot Panel — Backend

API em FastAPI responsável por tudo que precisa acessar o sistema de arquivos
ou controlar processos: criar/iniciar/parar bots, editar arquivos, ler `.env`,
monitorar CPU/RAM, e transmitir logs em tempo real via WebSocket.

O frontend (hospedado no Netlify) fala com esta API por HTTP/WebSocket.

## Instalação na VPS

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

# 4. Suba com Docker Compose (recomendado)
docker compose up -d --build

# Ou, sem Docker, direto com Python:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## HTTPS

O navegador bloqueia chamadas de um site HTTPS (Netlify) para uma API HTTP
simples. Você precisa de HTTPS no backend também. O jeito mais simples é
colocar um proxy reverso na frente:

```bash
# Exemplo rápido com Caddy (gera certificado automaticamente se você tiver
# um domínio apontado para o IP da VPS)
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

Se você usou Docker Compose, o `restart: unless-stopped` já garante que o
backend volta a rodar sozinho depois de um reboot da VPS. Os bots marcados
com "Iniciar automaticamente com o servidor" são iniciados pelo próprio
backend assim que ele sobe.

## Estrutura

```
backend/
  app/
    core/       # configuração, segurança (chave de API), banco de dados
    models/     # modelos SQLAlchemy e schemas Pydantic
    routers/    # rotas da API (bots, arquivos, env, monitoramento, console)
    services/   # lógica de negócio (processos, arquivos, docker, stats)
  bots_data/    # onde o código de cada bot fica salvo (criado automaticamente)
```
