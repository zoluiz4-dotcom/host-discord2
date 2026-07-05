"""
CineTrigger Bot — arquivo único.

Sistema completo de Discord bot com:
- Postagem automática de filmes (TMDB/OMDb -> Blogger)
- Sistema profissional de Tickets (categorias, cargos de suporte,
  transcript, logs, transferência entre categorias)
- Moderação (Lock, Unlock, Anti-Link)
- Auto Role
- Boas-vindas
- Anúncios com embeds personalizadas

Todas as credenciais (token do bot, chaves de API, credenciais do
Google) são carregadas de variáveis de ambiente através de um
arquivo .env na mesma pasta deste script. Nunca compartilhe o
arquivo .env nem o token com terceiros.

Para instalar as dependências:
    pip install discord.py aiohttp python-dotenv

Para rodar:
    python bot.py
"""

import asyncio
import copy
import datetime
import html as htmllib
import io
import json
import logging
import os
import re
import sys
import threading
import unicodedata
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("cinetrigger")


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 1 — CONFIGURAÇÕES E CONSTANTES
# ══════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────
# CREDENCIAIS (vindas do .env)
# ─────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
BLOG_ID = os.getenv("BLOG_ID", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/oauth2callback")

REQUIRED_ENV_VARS = {
    "DISCORD_TOKEN": DISCORD_TOKEN,
    "TMDB_API_KEY": TMDB_API_KEY,
    "OMDB_API_KEY": OMDB_API_KEY,
    "BLOG_ID": BLOG_ID,
    "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
}


def validar_variaveis_ambiente() -> list[str]:
    """Retorna a lista de variáveis de ambiente obrigatórias que estão vazias."""
    faltando = [nome for nome, valor in REQUIRED_ENV_VARS.items() if not valor]
    return faltando


# ─────────────────────────────────────────
# IDENTIDADE VISUAL CINETRIGGER
# ─────────────────────────────────────────
COR_PRIMARIA = 0xE63946      # Vermelho CineTrigger
COR_PRETO = 0x0A0A0A
COR_BRANCO = 0xFFFFFF
COR_CINZA_ESCURO = 0x1C1C1C
COR_SUCESSO = 0x2ECC71
COR_ERRO = 0xE63946
COR_AVISO = 0xF1C40F
COR_INFO = 0x3498DB

NOME_MARCA = "CineTrigger"

# ─────────────────────────────────────────
# API's de filmes
# ─────────────────────────────────────────
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_IMG_ORIG = "https://image.tmdb.org/t/p/original"
OMDB_BASE = "https://www.omdbapi.com/"
SCOPES_BLOGGER = "https://www.googleapis.com/auth/blogger"

IMAGEM_PADRAO = "https://i.imgur.com/8Ub4Uxl.png"

# ─────────────────────────────────────────
# CAMINHOS DE ARQUIVOS DE DADOS
# ─────────────────────────────────────────
PASTA_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(PASTA_DADOS, exist_ok=True)

ARQUIVO_CONFIG_GUILDS = os.path.join(PASTA_DADOS, "guild_config.json")
ARQUIVO_TICKETS = os.path.join(PASTA_DADOS, "tickets.json")
ARQUIVO_TOKEN_GOOGLE = os.path.join(PASTA_DADOS, "google_token.json")

# ─────────────────────────────────────────
# TRADUÇÃO DE GÊNEROS TMDB/OMDb -> PT
# ─────────────────────────────────────────
GENERO_PT = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Animation": "Animação",
    "Biography": "Biografia",
    "Comedy": "Comédia",
    "Crime": "Crime",
    "Documentary": "Documentário",
    "Drama": "Drama",
    "Family": "Família",
    "Fantasy": "Fantasia",
    "History": "História",
    "Horror": "Terror",
    "Music": "Musical",
    "Musical": "Musical",
    "Mystery": "Mistério",
    "Romance": "Romance",
    "Science Fiction": "Ficção Científica",
    "Sci-Fi": "Ficção Científica",
    "Short": "Curta",
    "Sport": "Esporte",
    "Sports": "Esporte",
    "Thriller": "Thriller",
    "War": "Guerra",
    "Western": "Faroeste",
    "TV Movie": "Filme de TV",
}


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 2 — PERSISTÊNCIA DE DADOS (JSON)
# ══════════════════════════════════════════════════════════════════

from typing import Any


def _config_padrao_guild() -> dict:
    """Estrutura padrão de configuração para um servidor novo."""
    return {
        "tickets": {
            "ativo": False,
            "categoria_id": None,
            "canal_mensagem_id": None,
            "mensagem_id": None,
            "canal_logs_id": None,
            "cargos_suporte": [],
            "max_tickets_por_usuario": 1,
            "contador": 0,
            "cor_embed": "#E63946",
            "logo_url": "",
            "thumbnail_url": "",
            "rodape": "CineTrigger • Sistema de Tickets",
            "titulo_mensagem": "Central de Atendimento",
            "descricao_mensagem": (
                "Clique no botão abaixo para abrir um ticket com nossa equipe de suporte."
            ),
            "tipos": {
                "suporte_geral": {"nome": "Suporte Geral", "emoji": "🛠️"},
                "reportar_bug": {"nome": "Reportar Bug", "emoji": "🐞"},
                "parceria": {"nome": "Parceria", "emoji": "🤝"},
                "sugestao": {"nome": "Sugestão", "emoji": "💡"},
                "duvidas": {"nome": "Dúvidas", "emoji": "❓"},
                "denuncia": {"nome": "Denúncia", "emoji": "⚠️"},
                "atendimento_vip": {"nome": "Atendimento VIP", "emoji": "👑"},
                "outro": {"nome": "Outro", "emoji": "📌"},
            },
        },
        "moderacao": {
            "anti_link_ativo": False,
            "anti_link_canais_ignorados": [],
            "anti_link_cargos_ignorados": [],
        },
        "autorole": {
            "ativo": False,
            "cargo_id": None,
        },
        "boas_vindas": {
            "ativo": False,
            "canal_id": None,
            "titulo": "Bem-vindo(a) ao servidor!",
            "mensagem": "Olá {membro}, seja bem-vindo(a) ao **{servidor}**! Esperamos que aproveite.",
            "cor_embed": "#E63946",
            "imagem_banner_url": "",
            "thumbnail_url": "",
            "mostrar_avatar": True,
        },
        "anuncios": {
            "cor_padrao": "#E63946",
            "logo_url": "",
            "rodape": "CineTrigger",
        },
        "identidade": {
            "logo_url": "",
            "thumbnail_url": "",
            "rodape": "CineTrigger",
            "cor_padrao": "#E63946",
        },
    }


class GerenciadorDados:
    """Gerencia leitura/escrita segura de arquivos JSON usados pelo bot."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cache_guilds: dict[str, Any] = self._carregar_arquivo(ARQUIVO_CONFIG_GUILDS)
        self._cache_tickets: dict[str, Any] = self._carregar_arquivo(ARQUIVO_TICKETS)

    # ─────────────────────────────────────────
    # I/O de baixo nível
    # ─────────────────────────────────────────
    @staticmethod
    def _carregar_arquivo(caminho: str) -> dict:
        if not os.path.exists(caminho):
            return {}
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                conteudo = arquivo.read().strip()
                if not conteudo:
                    return {}
                return json.loads(conteudo)
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _salvar_arquivo(caminho: str, dados: dict) -> None:
        pasta = os.path.dirname(caminho)
        os.makedirs(pasta, exist_ok=True)
        caminho_temp = f"{caminho}.tmp"
        with open(caminho_temp, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        os.replace(caminho_temp, caminho)

    # ─────────────────────────────────────────
    # Configuração por servidor
    # ─────────────────────────────────────────
    def _mesclar_com_padrao(self, config_guild: dict) -> dict:
        """Garante que chaves novas do padrão existam mesmo em configs antigas."""
        padrao = _config_padrao_guild()

        def mesclar(base: dict, atual: dict) -> dict:
            resultado = copy.deepcopy(base)
            for chave, valor in atual.items():
                if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
                    resultado[chave] = mesclar(resultado[chave], valor)
                else:
                    resultado[chave] = valor
            return resultado

        return mesclar(padrao, config_guild)

    async def obter_config_guild(self, guild_id: int) -> dict:
        async with self._lock:
            chave = str(guild_id)
            config_bruta = self._cache_guilds.get(chave, {})
            config_completa = self._mesclar_com_padrao(config_bruta)
            self._cache_guilds[chave] = config_completa
            return copy.deepcopy(config_completa)

    async def salvar_config_guild(self, guild_id: int, config: dict) -> None:
        async with self._lock:
            chave = str(guild_id)
            self._cache_guilds[chave] = config
            self._salvar_arquivo(ARQUIVO_CONFIG_GUILDS, self._cache_guilds)

    async def atualizar_config_guild(self, guild_id: int, caminho: list[str], valor: Any) -> dict:
        """
        Atualiza um valor aninhado na configuração do servidor.
        Exemplo: caminho=["tickets", "ativo"], valor=True
        """
        async with self._lock:
            chave = str(guild_id)
            config_bruta = self._cache_guilds.get(chave, {})
            config = self._mesclar_com_padrao(config_bruta)

            alvo = config
            for parte in caminho[:-1]:
                alvo = alvo.setdefault(parte, {})
            alvo[caminho[-1]] = valor

            self._cache_guilds[chave] = config
            self._salvar_arquivo(ARQUIVO_CONFIG_GUILDS, self._cache_guilds)
            return copy.deepcopy(config)

    # ─────────────────────────────────────────
    # Tickets ativos (dados voláteis persistidos)
    # ─────────────────────────────────────────
    async def obter_tickets_guild(self, guild_id: int) -> dict:
        async with self._lock:
            chave = str(guild_id)
            return copy.deepcopy(self._cache_tickets.get(chave, {}))

    async def salvar_ticket(self, guild_id: int, canal_id: int, dados_ticket: dict) -> None:
        async with self._lock:
            chave_guild = str(guild_id)
            chave_canal = str(canal_id)
            self._cache_tickets.setdefault(chave_guild, {})
            self._cache_tickets[chave_guild][chave_canal] = dados_ticket
            self._salvar_arquivo(ARQUIVO_TICKETS, self._cache_tickets)

    async def remover_ticket(self, guild_id: int, canal_id: int) -> None:
        async with self._lock:
            chave_guild = str(guild_id)
            chave_canal = str(canal_id)
            if chave_guild in self._cache_tickets:
                self._cache_tickets[chave_guild].pop(chave_canal, None)
                self._salvar_arquivo(ARQUIVO_TICKETS, self._cache_tickets)

    async def obter_ticket(self, guild_id: int, canal_id: int) -> dict | None:
        async with self._lock:
            chave_guild = str(guild_id)
            chave_canal = str(canal_id)
            ticket = self._cache_tickets.get(chave_guild, {}).get(chave_canal)
            return copy.deepcopy(ticket) if ticket else None

    async def contar_tickets_abertos_usuario(self, guild_id: int, usuario_id: int) -> int:
        async with self._lock:
            chave_guild = str(guild_id)
            tickets = self._cache_tickets.get(chave_guild, {})
            total = sum(
                1 for t in tickets.values()
                if t.get("usuario_id") == usuario_id and t.get("status") == "aberto"
            )
            return total


gerenciador_dados = GerenciadorDados()


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 3 — PERMISSÕES E EMBEDS PADRONIZADAS
# ══════════════════════════════════════════════════════════════════

class SemPermissaoError(app_commands.CheckFailure):
    """Erro lançado quando um membro sem permissão tenta usar um comando restrito."""


def apenas_administrador():
    """Restringe o comando a membros com permissão de Administrador."""

    async def predicado(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise SemPermissaoError("Este comando só pode ser usado dentro de um servidor.")
        if not isinstance(interaction.user, discord.Member):
            raise SemPermissaoError("Não foi possível verificar suas permissões.")
        if not interaction.user.guild_permissions.administrator:
            raise SemPermissaoError("Você precisa ser administrador para usar este comando.")
        return True

    return app_commands.check(predicado)


async def usuario_e_staff(membro: discord.Member, cargos_suporte: list[int]) -> bool:
    """Verifica se um membro é administrador ou possui algum cargo de suporte configurado."""
    if membro.guild_permissions.administrator:
        return True
    ids_cargos_membro = {cargo.id for cargo in membro.roles}
    return bool(ids_cargos_membro.intersection(set(cargos_suporte)))


def embed_sem_permissao(mensagem: str = "Você não tem permissão para usar este comando.") -> discord.Embed:
    return discord.Embed(
        title="Acesso negado",
        description=mensagem,
        color=COR_ERRO,
    )


def _cor_para_int(cor_hex: str | None, cor_padrao: int = COR_PRIMARIA) -> int:
    if not cor_hex:
        return cor_padrao
    try:
        return int(cor_hex.lstrip("#"), 16)
    except (ValueError, TypeError):
        return cor_padrao


def embed_base(
    titulo: str,
    descricao: str = "",
    cor_hex: str | None = None,
    identidade: dict | None = None,
) -> discord.Embed:
    """
    Cria um embed já com a identidade visual do CineTrigger aplicada
    (logo como thumbnail, thumbnail customizada e rodapé), caso configurados.
    """
    identidade = identidade or {}
    cor = _cor_para_int(cor_hex or identidade.get("cor_padrao"))

    embed = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    thumbnail_url = identidade.get("thumbnail_url")
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    logo_url = identidade.get("logo_url")
    if logo_url:
        embed.set_author(name=NOME_MARCA, icon_url=logo_url)

    rodape = identidade.get("rodape") or NOME_MARCA
    if logo_url:
        embed.set_footer(text=rodape, icon_url=logo_url)
    else:
        embed.set_footer(text=rodape)

    return embed


def embed_sucesso(titulo: str, descricao: str = "") -> discord.Embed:
    return discord.Embed(title=f"✅ {titulo}", description=descricao, color=COR_SUCESSO)


def embed_erro(titulo: str, descricao: str = "") -> discord.Embed:
    return discord.Embed(title=f"❌ {titulo}", description=descricao, color=COR_ERRO)


def embed_aviso(titulo: str, descricao: str = "") -> discord.Embed:
    return discord.Embed(title=f"⚠️ {titulo}", description=descricao, color=COR_AVISO)


def embed_info(titulo: str, descricao: str = "") -> discord.Embed:
    return discord.Embed(title=f"ℹ️ {titulo}", description=descricao, color=COR_INFO)





# ══════════════════════════════════════════════════════════════════
# SEÇÃO 4 — BUSCA DE FILMES (TMDB e OMDb)
# ══════════════════════════════════════════════════════════════════



def remover_acentos(texto: str) -> str:
    return "".join(
        caractere for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )


def formatar_duracao(minutos_totais: int) -> str:
    if not minutos_totais:
        return ""
    horas, minutos = divmod(minutos_totais, 60)
    return f"{horas}h{minutos:02d}min" if horas else f"{minutos}min"


# ─────────────────────────────────────────
# TMDB
# ─────────────────────────────────────────
async def tmdb_buscar(sessao: aiohttp.ClientSession, consulta: str, idioma: str = "pt-BR") -> dict | None:
    parametros = {
        "api_key": TMDB_API_KEY,
        "query": consulta,
        "language": idioma,
        "include_adult": "false",
    }
    try:
        async with sessao.get(f"{TMDB_BASE}/search/movie", params=parametros) as resposta:
            dados = await resposta.json()
            resultados = dados.get("results", [])
            return resultados[0] if resultados else None
    except aiohttp.ClientError:
        return None


async def tmdb_detalhes(sessao: aiohttp.ClientSession, tmdb_id: int, idioma: str = "pt-BR") -> dict | None:
    parametros = {
        "api_key": TMDB_API_KEY,
        "language": idioma,
        "append_to_response": "credits,release_dates",
    }
    try:
        async with sessao.get(f"{TMDB_BASE}/movie/{tmdb_id}", params=parametros) as resposta:
            dados = await resposta.json()
            return dados if dados.get("id") else None
    except aiohttp.ClientError:
        return None


async def buscar_filme_tmdb(nome: str) -> dict | None:
    nome_sem_acento = remover_acentos(nome)
    tentativas = list(dict.fromkeys([nome, nome_sem_acento]))

    async with aiohttp.ClientSession() as sessao:
        for consulta in tentativas:
            for idioma in ("pt-BR", "en-US"):
                resultado = await tmdb_buscar(sessao, consulta, idioma)
                if resultado:
                    tmdb_id = resultado["id"]
                    detalhes = await tmdb_detalhes(sessao, tmdb_id, idioma="pt-BR")
                    if detalhes:
                        return detalhes
    return None


def tmdb_para_dados(tmdb: dict, audio: str, ano_atual: int) -> dict:
    titulo = tmdb.get("title") or tmdb.get("original_title", "")
    poster_path = tmdb.get("poster_path") or ""
    poster = f"{TMDB_IMG_BASE}{poster_path}" if poster_path else ""
    backdrop_path = tmdb.get("backdrop_path") or ""
    backdrop = f"{TMDB_IMG_ORIG}{backdrop_path}" if backdrop_path else poster
    lancamento = tmdb.get("release_date", "") or ""
    ano = lancamento[:4] if lancamento else ""
    nota_bruta = tmdb.get("vote_average", 0)
    nota = f"{nota_bruta:.1f}" if nota_bruta else ""
    duracao_minutos = tmdb.get("runtime") or 0
    duracao = formatar_duracao(duracao_minutos)
    sinopse = tmdb.get("overview", "") or ""
    generos_originais = [genero["name"] for genero in tmdb.get("genres", [])]
    generos_pt = [GENERO_PT.get(genero, genero) for genero in generos_originais]

    badge = "Lançamento"
    if ano:
        try:
            badge = "Lançamento" if int(ano) >= ano_atual - 1 else "Novo"
        except ValueError:
            badge = "Novo"

    tmdb_id = tmdb.get("id", "")
    tmdb_link = f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else ""
    imdb_id = tmdb.get("imdb_id", "")
    imdb_link = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else ""

    return {
        "titulo": titulo,
        "poster": poster,
        "backdrop": backdrop,
        "ano": ano,
        "nota": nota,
        "dur": duracao,
        "sinopse": sinopse,
        "generos_pt": generos_pt,
        "badge": badge,
        "tmdb_id": tmdb_id,
        "tmdb_link": tmdb_link,
        "imdb_id": imdb_id,
        "imdb_link": imdb_link,
        "extra": {},
    }


# ─────────────────────────────────────────
# OMDb
# ─────────────────────────────────────────
async def omdb_por_imdb_id(sessao: aiohttp.ClientSession, imdb_id: str) -> dict | None:
    if not imdb_id:
        return None
    parametros = {"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "full"}
    try:
        async with sessao.get(OMDB_BASE, params=parametros) as resposta:
            dados = await resposta.json()
            if dados.get("Response") == "True":
                return dados
    except aiohttp.ClientError:
        pass
    return None


async def omdb_por_titulo(sessao: aiohttp.ClientSession, titulo: str, ano: str | None = None) -> dict | None:
    parametros = {"apikey": OMDB_API_KEY, "t": titulo, "type": "movie", "plot": "full"}
    if ano:
        parametros["y"] = ano
    try:
        async with sessao.get(OMDB_BASE, params=parametros) as resposta:
            dados = await resposta.json()
            if dados.get("Response") == "True":
                return dados
    except aiohttp.ClientError:
        pass
    return None


async def buscar_filme_omdb(nome: str) -> dict | None:
    nome_sem_acento = remover_acentos(nome)
    tentativas = list(dict.fromkeys([nome, nome_sem_acento]))

    async with aiohttp.ClientSession() as sessao:
        for consulta in tentativas:
            resultado = await omdb_por_titulo(sessao, consulta)
            if resultado:
                return resultado
    return None


def extrair_dados_extras_omdb(omdb: dict) -> dict:
    if not omdb:
        return {}
    extra = {}

    nota_imdb = omdb.get("imdbRating", "")
    if nota_imdb and nota_imdb != "N/A":
        votos_imdb = omdb.get("imdbVotes", "")
        extra["imdb_nota"] = nota_imdb
        extra["imdb_votos"] = votos_imdb if votos_imdb and votos_imdb != "N/A" else ""

    for avaliacao in omdb.get("Ratings", []) or []:
        fonte = avaliacao.get("Source", "")
        valor = avaliacao.get("Value", "")
        if fonte == "Rotten Tomatoes" and valor:
            extra["rotten_tomatoes"] = valor
        elif fonte == "Metacritic" and valor:
            extra["metascore_ratings"] = valor

    campos_simples = {
        "Metascore": "metascore",
        "Rated": "classificacao",
        "BoxOffice": "bilheteria",
        "Awards": "premios",
        "Director": "diretor",
        "Actors": "elenco",
        "Country": "pais",
        "Language": "idioma_original",
    }
    for campo_omdb, campo_extra in campos_simples.items():
        valor = omdb.get(campo_omdb, "")
        if valor and valor != "N/A":
            extra[campo_extra] = valor

    return extra


def omdb_para_dados(omdb: dict, audio: str, ano_atual: int) -> dict:
    titulo = omdb.get("Title", "") or ""
    poster = omdb.get("Poster", "") or ""
    if poster in ("N/A", ""):
        poster = ""
    backdrop = poster
    ano_bruto = omdb.get("Year", "") or ""
    ano = ano_bruto[:4] if ano_bruto else ""
    nota_imdb = omdb.get("imdbRating", "") or ""
    nota = nota_imdb if nota_imdb and nota_imdb != "N/A" else ""

    duracao = ""
    runtime_bruto = omdb.get("Runtime", "") or ""
    try:
        minutos = int(runtime_bruto.replace(" min", "").strip())
        duracao = formatar_duracao(minutos)
    except (ValueError, AttributeError):
        pass

    sinopse = omdb.get("Plot", "") or ""
    if sinopse == "N/A":
        sinopse = ""

    generos_brutos = [genero.strip() for genero in (omdb.get("Genre", "") or "").split(",") if genero.strip()]
    generos_pt = [GENERO_PT.get(genero, genero) for genero in generos_brutos]

    badge = "Lançamento" if (ano and ano.isdigit() and int(ano) >= ano_atual - 1) else "Novo"

    imdb_id = omdb.get("imdbID", "") or ""
    imdb_link = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else ""

    return {
        "titulo": titulo,
        "poster": poster,
        "backdrop": backdrop,
        "ano": ano,
        "nota": nota,
        "dur": duracao,
        "sinopse": sinopse,
        "generos_pt": generos_pt,
        "badge": badge,
        "tmdb_id": "",
        "tmdb_link": "",
        "imdb_id": imdb_id,
        "imdb_link": imdb_link,
        "extra": extrair_dados_extras_omdb(omdb),
    }


async def enriquecer_com_omdb(dados: dict, ano_atual: int) -> dict:
    """Complementa dados vindos do TMDB com informações extras da OMDb (nota IMDb, Rotten Tomatoes, etc)."""
    omdb_dados = None
    imdb_id = dados.get("imdb_id", "")

    async with aiohttp.ClientSession() as sessao:
        if imdb_id:
            omdb_dados = await omdb_por_imdb_id(sessao, imdb_id)
        if not omdb_dados:
            omdb_dados = await omdb_por_titulo(sessao, dados.get("titulo", ""), dados.get("ano") or None)

    if omdb_dados:
        if not dados.get("poster"):
            poster_omdb = omdb_dados.get("Poster", "")
            if poster_omdb and poster_omdb != "N/A":
                dados["poster"] = poster_omdb
        if not dados.get("backdrop"):
            dados["backdrop"] = dados.get("poster") or ""
        dados["extra"] = extrair_dados_extras_omdb(omdb_dados)
    else:
        dados.setdefault("extra", {})

    if not dados.get("poster"):
        dados["poster"] = IMAGEM_PADRAO
    if not dados.get("backdrop"):
        dados["backdrop"] = dados.get("poster") or IMAGEM_PADRAO

    return dados


def gerar_labels(dados: dict, audio: str, ano_atual: int) -> list[str]:
    labels = []
    ano = dados.get("ano", "")

    try:
        labels.append("Lançamento" if ano and int(ano) >= ano_atual - 1 else "Novo")
    except (ValueError, TypeError):
        labels.append("Novo")

    if ano and ano != "N/A":
        labels.append(ano)

    nota = dados.get("nota", "")
    if nota:
        try:
            labels.append(f"★{float(nota):.1f}")
        except ValueError:
            pass

    duracao = dados.get("dur", "")
    if duracao:
        labels.append(duracao)

    if audio:
        labels.append(audio)

    for genero in dados.get("generos_pt", []):
        if genero and genero not in labels:
            labels.append(genero)

    classificacao = dados.get("extra", {}).get("classificacao", "")
    if classificacao and classificacao not in labels:
        labels.append(classificacao)

    labels.append("Filme")
    return labels


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 5 — AUTENTICAÇÃO OAUTH2 E POSTAGEM NO BLOGGER
# ══════════════════════════════════════════════════════════════════


_codigo_autorizacao = {"valor": None}


class _ManipuladorOAuth(BaseHTTPRequestHandler):
    """
    Servidor HTTP único do processo. No Render (Web Service) ele precisa
    escutar em 0.0.0.0:$PORT para o serviço ser considerado "no ar" pelo
    health check, e é o MESMO endpoint que recebe o redirect do OAuth do
    Google (rota /oauth2callback). Por isso REDIRECT_URI no .env deve ser
    a URL pública do serviço no Render + "/oauth2callback", e não mais
    "http://localhost:8080".
    """

    def do_GET(self):
        caminho = urlparse(self.path).path
        parametros = parse_qs(urlparse(self.path).query)

        if caminho == "/oauth2callback" and "code" in parametros:
            _codigo_autorizacao["valor"] = parametros["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"""<html><body style="font-family:sans-serif;background:#0A0A0A;color:#fff;
                display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
                <div style="text-align:center">
                  <h1 style="color:#E63946">Autorizado!</h1>
                  <p>Pode fechar essa aba e voltar para o Discord.</p>
                </div></body></html>"""
            )
            return

        # Health check do Render (e qualquer outra rota) recebe 200 simples.
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"CineTrigger Bot online.")

    def log_message(self, *args):
        pass


def _iniciar_servidor_http():
    """
    Inicia o servidor HTTP unico do processo, escutando na porta que o
    Render define via variavel de ambiente PORT (obrigatorio para Web
    Services). Roda para sempre em background numa thread separada.
    """
    porta = int(os.getenv("PORT", "8080"))
    servidor = HTTPServer(("0.0.0.0", porta), _ManipuladorOAuth)
    logger.info("Servidor HTTP (health check + OAuth callback) escutando na porta %d", porta)
    servidor.serve_forever()


async def obter_token_acesso() -> str | None:
    if not os.path.exists(ARQUIVO_TOKEN_GOOGLE):
        return None
    try:
        with open(ARQUIVO_TOKEN_GOOGLE, "r", encoding="utf-8") as arquivo:
            dados_token = json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        return None

    refresh_token = dados_token.get("refresh_token")
    if not refresh_token:
        return None
    return await _renovar_token_acesso(refresh_token)


async def _renovar_token_acesso(refresh_token: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as sessao:
            async with sessao.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            ) as resposta:
                dados = await resposta.json()
    except aiohttp.ClientError:
        return None

    novo_token = dados.get("access_token")
    if not novo_token:
        return None

    dados_salvos = {}
    if os.path.exists(ARQUIVO_TOKEN_GOOGLE):
        try:
            with open(ARQUIVO_TOKEN_GOOGLE, "r", encoding="utf-8") as arquivo:
                dados_salvos = json.load(arquivo)
        except (json.JSONDecodeError, OSError):
            dados_salvos = {}

    dados_salvos["access_token"] = novo_token
    with open(ARQUIVO_TOKEN_GOOGLE, "w", encoding="utf-8") as arquivo:
        json.dump(dados_salvos, arquivo)

    return novo_token


async def autorizar_blogger(interaction: discord.Interaction) -> str | None:
    url_autorizacao = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES_BLOGGER,
        "access_type": "offline",
        "prompt": "consent",
    })

    embed = discord.Embed(
        title="Autorizar Blogger",
        description=(
            "**1.** Clique no link abaixo\n"
            "**2.** Faça login com sua conta Google\n"
            "**3.** Autorize o acesso\n"
            "**4.** Volte aqui e use `/filme` normalmente\n\n"
            f"[Clique aqui para autorizar]({url_autorizacao})"
        ),
        color=COR_PRIMARIA,
    )
    embed.set_footer(text="Essa autorização só precisa ser feita uma vez.")
    await interaction.followup.send(embed=embed, ephemeral=True)

    # O servidor HTTP já está rodando desde o início do processo (main),
    # então aqui só esperamos o codigo de autorizacao chegar via /oauth2callback.
    for _ in range(120):
        await asyncio.sleep(1)
        if _codigo_autorizacao["valor"]:
            break

    if not _codigo_autorizacao["valor"]:
        await interaction.followup.send(
            "Tempo esgotado. Use `/autorizar` e tente novamente.", ephemeral=True
        )
        return None

    codigo = _codigo_autorizacao["valor"]
    _codigo_autorizacao["valor"] = None

    try:
        async with aiohttp.ClientSession() as sessao:
            async with sessao.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": codigo,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            ) as resposta:
                dados_token = await resposta.json()
    except aiohttp.ClientError:
        await interaction.followup.send("Erro de conexão ao obter token.", ephemeral=True)
        return None

    if "access_token" not in dados_token:
        await interaction.followup.send("Erro ao obter token. Tente novamente.", ephemeral=True)
        return None

    with open(ARQUIVO_TOKEN_GOOGLE, "w", encoding="utf-8") as arquivo:
        json.dump(dados_token, arquivo)

    return dados_token["access_token"]


async def postar_no_blogger(token_acesso: str, titulo: str, conteudo_html: str, labels: list[str]):
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/"
    cabecalhos = {
        "Authorization": f"Bearer {token_acesso}",
        "Content-Type": "application/json",
    }
    corpo = {"title": titulo, "content": conteudo_html, "labels": labels}

    try:
        async with aiohttp.ClientSession() as sessao:
            async with sessao.post(url, headers=cabecalhos, json=corpo) as resposta:
                dados = await resposta.json()
                if resposta.status in (200, 201):
                    return dados.get("url"), dados.get("id")
                return None, None
    except aiohttp.ClientError:
        return None, None


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 6 — GERAÇÃO DO HTML DA PÁGINA DE FILME
# ══════════════════════════════════════════════════════════════════


def gerar_html_pagina_filme(
    titulo, video_url, poster_url, backdrop_url, ano, nota, dur,
    generos_pt, audio, sinopse, badge, tmdb_link, imdb_link, extra=None,
):
    extra = extra or {}
    t = htmllib.escape(titulo)
    sin = htmllib.escape(sinopse[:400]) if sinopse else ""
    p = poster_url or IMAGEM_PADRAO
    bg = backdrop_url or poster_url or IMAGEM_PADRAO
    n = nota if nota else ""
    d = dur if dur else ""
    g_main = generos_pt[0] if generos_pt else ""
    a = ano if ano else ""
    dub = audio if audio else ""

    badges_html = ""
    if badge: badges_html += f'<span class="badge badge-red">{badge}</span>'
    if a: badges_html += f'<span class="badge">{a}</span>'
    if d: badges_html += f'<span class="badge">{d}</span>'
    if g_main: badges_html += f'<span class="badge">{g_main}</span>'
    if dub: badges_html += f'<span class="badge">{dub}</span>'

    meta_parts = []
    if n: meta_parts.append(f'<span class="star">&#9733; {n}</span>')
    if d: meta_parts.append(f'<span>{d}</span>')
    if dub: meta_parts.append(f'<span>{dub}</span>')
    meta_html = '<span class="dot"></span>'.join(meta_parts)

    sin_block = f'<div class="card"><div class="card-label">Sinopse</div><p class="synopsis">{sin}</p></div>' if sin else ""
    tags_html = "".join(f'<span class="tag">{g}</span>' for g in generos_pt)
    tags_block = f'<div class="card"><div class="card-label">Gêneros</div><div class="tags-wrap">{tags_html}</div></div>' if len(generos_pt) > 1 else ""

    external_chips = ""
    if tmdb_link:
        external_chips += f'<a class="quality-chip" href="{tmdb_link}" target="_blank"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg><div class="chip-label"><span>TMDB</span><span>Ver página</span></div></a>'
    if imdb_link:
        external_chips += f'<a class="quality-chip" href="{imdb_link}" target="_blank"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg><div class="chip-label"><span>IMDB</span><span>Ver página</span></div></a>'

    imdb_nota = extra.get("imdb_nota", "")
    rotten_tomatoes = extra.get("rotten_tomatoes", "")
    metascore = extra.get("metascore", "")
    classificacao = extra.get("classificacao", "")
    bilheteria = extra.get("bilheteria", "")
    premios = extra.get("premios", "")

    info_rows = "".join([
        f'<div class="info-item"><div class="info-label">Ano</div><div class="info-value">{a}</div></div>' if a else "",
        f'<div class="info-item"><div class="info-label">Duração</div><div class="info-value">{d}</div></div>' if d else "",
        f'<div class="info-item"><div class="info-label">Áudio</div><div class="info-value">{dub}</div></div>' if dub else "",
        f'<div class="info-item"><div class="info-label">Nota TMDB</div><div class="info-value gold">&#9733; {n}</div></div>' if n else "",
        f'<div class="info-item"><div class="info-label">Nota IMDb</div><div class="info-value gold">&#9733; {imdb_nota}</div></div>' if imdb_nota else "",
        f'<div class="info-item"><div class="info-label">Rotten Tomatoes</div><div class="info-value">&#127813; {rotten_tomatoes}</div></div>' if rotten_tomatoes else "",
        f'<div class="info-item"><div class="info-label">Metascore</div><div class="info-value">{metascore}</div></div>' if metascore else "",
        f'<div class="info-item"><div class="info-label">Classificação</div><div class="info-value">{classificacao}</div></div>' if classificacao else "",
        f'<div class="info-item"><div class="info-label">Bilheteria</div><div class="info-value">{bilheteria}</div></div>' if bilheteria else "",
        f'<div class="info-item"><div class="info-label">Gênero</div><div class="info-value">{", ".join(generos_pt[:2])}</div></div>' if generos_pt else "",
    ])

    premios_block = f'<div class="card"><div class="card-label">Prêmios</div><p class="synopsis">{htmllib.escape(premios)}</p></div>' if premios else ""

    return f"""<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{t} — CineStream</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--red:#E63946;--glow:rgba(230,57,70,0.35);--bg:#08080D;--s1:#0F0F17;--s2:#14141E;--border:rgba(255,255,255,0.06);--border2:rgba(255,255,255,0.11);--text:#EEEEF5;--sub:#9898B0;--gold:#FFD166}}
body{{background:var(--bg);font-family:'Inter',sans-serif;color:var(--text);min-height:100vh;overflow-x:hidden}}
nav{{position:fixed;top:0;left:0;right:0;z-index:300;height:54px;background:rgba(8,8,13,0.93);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;gap:10px}}
.nav-back{{display:flex;align-items:center;gap:5px;color:var(--sub);font-size:13px;font-weight:600;text-decoration:none;padding:6px 10px;border-radius:8px;transition:color .15s,background .15s}}
.nav-back:hover{{color:var(--text);background:rgba(255,255,255,.06)}}
.nav-back svg{{width:17px;height:17px}}
.nav-title{{font-size:13px;font-weight:700;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:0 8px}}
.logo{{font-size:17px;font-weight:900;letter-spacing:-.04em;color:#fff;text-decoration:none}}
.logo em{{color:var(--red);font-style:normal}}
.hero{{position:relative;width:100%;overflow:hidden;margin-top:54px}}
.hero-img{{width:100%;height:100%;object-fit:cover;object-position:center 18%;filter:brightness(.42) saturate(1.1);display:block}}
.hero::after{{content:'';position:absolute;inset:0;background:linear-gradient(to bottom,rgba(8,8,13,.1) 0%,transparent 22%,rgba(8,8,13,.82) 64%,var(--bg) 100%),linear-gradient(to right,rgba(8,8,13,.84) 0%,rgba(8,8,13,.28) 52%,transparent 78%)}}
.hero-content{{position:absolute;bottom:0;left:0;right:0;z-index:2}}
.badge{{font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;padding:3px 8px;border-radius:4px;border:1px solid rgba(255,255,255,.11);background:rgba(255,255,255,.07);color:#9898B0}}
.badge-red{{background:#E63946;border-color:#E63946;color:#fff}}
.badge-row{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}}
.hero-title{{font-weight:900;line-height:1.04;letter-spacing:-.025em;color:#fff;text-shadow:0 2px 22px rgba(0,0,0,.6)}}
.hero-meta{{display:flex;gap:12px;align-items:center;font-size:13px;color:#9898B0;font-weight:500;flex-wrap:wrap}}
.hero-meta .dot{{width:3px;height:3px;border-radius:50%;background:#9898B0}}
.star{{color:#FFD166;font-weight:700}}
@media(min-width:641px){{.hero{{height:84vh;min-height:460px}}.hero-content{{padding:0 28px 34px;max-width:780px}}.badge-row{{margin-bottom:12px}}.hero-title{{font-size:clamp(26px,5.5vw,56px);margin-bottom:10px}}}}
@media(max-width:640px){{.hero{{height:50vh;min-height:255px;max-height:355px}}.hero-content{{padding:0 14px 16px}}.badge-row{{gap:5px;margin-bottom:7px}}.badge{{font-size:9px;padding:2px 6px}}.hero-title{{font-size:clamp(17px,5.5vw,26px);margin-bottom:7px}}.hero-meta{{font-size:11px;gap:8px}}nav{{padding:0 14px}}}}
.container{{max-width:720px;margin:0 auto;padding:0 18px 80px}}
@media(max-width:640px){{.container{{padding:0 14px 80px}}}}
.btn-play{{display:flex;align-items:center;justify-content:center;gap:11px;width:100%;padding:18px;margin-top:-20px;margin-bottom:12px;background:var(--red);color:#fff;font-size:16px;font-weight:700;text-decoration:none;border-radius:15px;border:none;cursor:pointer;position:relative;overflow:hidden;z-index:5;box-shadow:0 0 0 1px rgba(230,57,70,.3),0 8px 28px var(--glow);animation:pulse 2.8s ease-out infinite}}
.btn-play::before{{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,.13) 0%,transparent 58%)}}
@keyframes pulse{{0%{{box-shadow:0 0 0 0 var(--glow),0 8px 28px var(--glow)}}70%{{box-shadow:0 0 0 10px rgba(230,57,70,0),0 8px 28px var(--glow)}}100%{{box-shadow:0 0 0 0 rgba(230,57,70,0),0 8px 28px var(--glow)}}}}
.play-icon{{width:24px;height:24px;background:rgba(255,255,255,.2);border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.play-icon svg{{width:10px;height:10px;margin-left:2px}}
.quality-row{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}}
.quality-chip{{display:flex;align-items:center;gap:7px;padding:10px 14px;background:var(--s1);border:1px solid var(--border);border-radius:11px;color:var(--sub);font-size:12px;font-weight:600;cursor:pointer;transition:background .15s,color .15s,border-color .15s;text-decoration:none}}
.quality-chip:hover{{background:var(--s2);color:var(--text);border-color:var(--border2)}}
.chip-label span:first-child{{display:block;color:var(--text);font-size:11px;font-weight:700}}
.chip-label span:last-child{{font-size:10px;color:var(--sub)}}
.actions-row{{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:22px}}
.btn-sec{{display:flex;align-items:center;justify-content:center;gap:7px;padding:13px 12px;background:var(--s1);border:1px solid var(--border);border-radius:11px;color:var(--sub);font-size:12px;font-weight:600;cursor:pointer;transition:background .15s,color .15s,border-color .15s;font-family:inherit}}
.btn-sec:hover{{background:var(--s2);color:var(--text);border-color:var(--border2)}}
.btn-sec svg{{width:16px;height:16px;flex-shrink:0}}
.card{{background:var(--s1);border:1px solid var(--border);border-radius:15px;padding:18px;margin-bottom:11px}}
.card-label{{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--red);margin-bottom:11px;display:flex;align-items:center;gap:7px}}
.card-label::after{{content:'';flex:1;height:1px;background:var(--border)}}
.synopsis{{font-size:14px;color:#BEBECF;line-height:1.82}}
.info-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:10px}}
.info-item{{background:var(--s2);border-radius:10px;padding:11px 14px}}
.info-label{{font-size:10px;color:var(--sub);font-weight:600;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}}
.info-value{{font-size:13px;font-weight:700;color:var(--text)}}
.info-value.gold{{color:var(--gold)}}
.tags-wrap{{display:flex;flex-wrap:wrap;gap:7px}}
.tag{{font-size:11px;font-weight:600;padding:5px 11px;border-radius:20px;border:1px solid var(--border);background:var(--s2);color:var(--sub)}}
.support{{background:var(--s1);border:1px solid var(--border);border-radius:15px;padding:16px 18px;display:flex;align-items:flex-start;gap:13px}}
.support-icon{{width:36px;height:36px;background:rgba(230,57,70,.1);border:1px solid rgba(230,57,70,.2);border-radius:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.support-icon svg{{width:17px;height:17px;color:var(--red)}}
.sup-title{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px}}
.sup-desc{{font-size:12px;color:var(--sub);line-height:1.6}}
.link-red{{color:var(--red);font-weight:600;text-decoration:none}}
</style>
</head>
<body>
<nav>
  <a class="nav-back" href="javascript:history.back()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 18l-6-6 6-6"/></svg>
    Voltar
  </a>
  <div class="nav-title">{t}</div>
  <a class="logo" href="/">Cine<em>Stream</em></a>
</nav>

<div class="hero">
  <img class="hero-img" src="{bg}" alt="{t}">
  <div class="hero-content">
    <div class="badge-row">{badges_html}</div>
    <h1 class="hero-title">{t}</h1>
    <div class="hero-meta">{meta_html}</div>
  </div>
</div>

<div class="container">
  <a class="btn-play" href="{video_url}" target="_blank">
    <span class="play-icon"><svg viewBox="0 0 10 12" fill="white"><path d="M1 1L9 6L1 11V1Z"/></svg></span>
    Assistir Agora
  </a>

  <div class="quality-row">
    <a class="quality-chip" href="{video_url}" target="_blank">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/></svg>
      <div class="chip-label"><span>Assistir Online</span><span>FHD 1080p</span></div>
    </a>
    <a class="quality-chip" href="{video_url}" download>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      <div class="chip-label"><span>Download MP4</span><span>Salvar arquivo</span></div>
    </a>
    {external_chips}
  </div>

  <div class="actions-row">
    <button class="btn-sec" onclick="toggleLista()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>
      <span id="listaText">Minha Lista</span>
    </button>
    <button class="btn-sec" onclick="if(navigator.share)navigator.share({{title:'{t}',url:location.href}});else navigator.clipboard.writeText(location.href)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98"/></svg>
      Compartilhar
    </button>
  </div>

  {'<div class="card"><div class="card-label">Informações</div><div class="info-grid">' + info_rows + '</div></div>' if info_rows else ''}
  {sin_block}
  {tags_block}
  {premios_block}

  <div class="support">
    <div class="support-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
    </div>
    <div>
      <div class="sup-title">Problemas com o player?</div>
      <div class="sup-desc">Tente atualizar a página ou <a class="link-red" href="/">voltar ao início</a>.</div>
    </div>
  </div>
</div>

<script>
(function(){{
  var t='{t.replace("'", "\\'")}',c='{p}';
  function check(){{
    var l=JSON.parse(localStorage.getItem('cs_lista')||'[]');
    document.getElementById('listaText').textContent=l.some(function(x){{return x.titulo===t;}})? 'Na Lista ✓':'Minha Lista';
  }}
  window.toggleLista=function(){{
    var l=JSON.parse(localStorage.getItem('cs_lista')||'[]'),i=l.findIndex(function(x){{return x.titulo===t;}});
    if(i>=0)l.splice(i,1);else l.push({{titulo:t,capa:c,url:location.href}});
    localStorage.setItem('cs_lista',JSON.stringify(l));check();
  }};
  check();
  try{{var h=JSON.parse(localStorage.getItem('cs_history')||'[]').filter(function(x){{return x.titulo!==t;}});h.unshift({{titulo:t,capa:c,url:location.href}});localStorage.setItem('cs_history',JSON.stringify(h.slice(0,20)));}}catch(e){{}}
}})();
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 7 — COG: COMANDOS DE FILME (/autorizar e /filme)
# ══════════════════════════════════════════════════════════════════


class ConfirmarPostagemView(discord.ui.View):
    """Botões de confirmação antes de publicar o filme no Blogger."""

    def __init__(self, autor_id: int):
        super().__init__(timeout=180)
        self.autor_id = autor_id
        self.valor: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "Apenas quem executou o comando pode confirmar esta ação.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Confirmar e Postar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        self.valor = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        self.valor = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class FilmeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="autorizar", description="Autorizar o bot a postar no Blogger")
    @app_commands.default_permissions(administrator=True)
    @apenas_administrador()
    async def cmd_autorizar(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            token = await autorizar_blogger(interaction)
            if token:
                await interaction.followup.send("Autorizado com sucesso! Agora use `/filme`.", ephemeral=True)
        except Exception:
            logger.exception("Erro no comando /autorizar")
            await interaction.followup.send(
                "Ocorreu um erro inesperado ao autorizar. Tente novamente.", ephemeral=True
            )

    @app_commands.command(name="filme", description="Postar filme no CineStream — só precisa do nome e do MP4")
    @app_commands.default_permissions(administrator=True)
    @apenas_administrador()
    @app_commands.describe(
        nome="Nome do filme em português (ex: Pânico 7, Vingadores)",
        mp4="Link direto do arquivo .mp4",
        audio="Tipo de áudio (padrão: Dublado)",
    )
    @app_commands.choices(audio=[
        app_commands.Choice(name="Dublado", value="Dublado"),
        app_commands.Choice(name="Legendado", value="Legendado"),
        app_commands.Choice(name="Dual Áudio", value="Dual Audio"),
    ])
    async def cmd_filme(
        self,
        interaction: discord.Interaction,
        nome: str,
        mp4: str,
        audio: app_commands.Choice[str] = None,
    ):
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            return

        audio_valor = audio.value if audio else "Dublado"
        ano_atual = datetime.datetime.now().year

        try:
            mensagem = await interaction.followup.send("Buscando informações do filme no TMDB...")
        except discord.HTTPException:
            logger.exception("Falha ao enviar mensagem inicial de /filme")
            return

        try:
            dados = await self._buscar_dados_filme(mensagem, nome, audio_valor, ano_atual)
        except Exception:
            logger.exception("Erro ao buscar dados do filme")
            await self._editar_seguro(mensagem, content="Ocorreu um erro ao buscar os dados do filme. Tente novamente.")
            return

        if dados is None:
            return

        try:
            labels = gerar_labels(dados, audio_valor, ano_atual)
        except Exception:
            logger.exception("Erro ao gerar labels do filme")
            labels = ["Filme"]

        embed = self._montar_embed_preview(dados, audio_valor, labels)

        view = ConfirmarPostagemView(autor_id=interaction.user.id)
        await self._editar_seguro(
            mensagem, content="**Confira os dados antes de postar:**", embed=embed, view=view
        )

        await view.wait()

        if view.valor is None:
            await self._editar_seguro(mensagem, content="Tempo esgotado. Use `/filme` novamente.", embed=None, view=None)
            return

        if not view.valor:
            await self._editar_seguro(mensagem, content="Postagem cancelada.", embed=None, view=None)
            return

        await self._publicar_no_blogger(mensagem, dados, mp4, audio_valor, labels)

    async def _buscar_dados_filme(self, mensagem: discord.Message, nome: str, audio_valor: str, ano_atual: int) -> dict | None:
        tmdb_bruto = await buscar_filme_tmdb(nome)

        if tmdb_bruto:
            dados = tmdb_para_dados(tmdb_bruto, audio_valor, ano_atual)
            await self._editar_seguro(mensagem, content="Complementando dados com a OMDb...")
            dados = await enriquecer_com_omdb(dados, ano_atual)
            return dados

        await self._editar_seguro(mensagem, content="Não encontrei no TMDB, tentando na OMDb...")
        omdb_bruto = await buscar_filme_omdb(nome)

        if not omdb_bruto:
            await self._editar_seguro(
                mensagem,
                content=(
                    f"Não encontrei **{nome}** no TMDB nem na OMDb.\n"
                    f"Dica: tente o nome em inglês (ex: `Scream 7` em vez de `Pânico 7`)."
                ),
            )
            return None

        dados = omdb_para_dados(omdb_bruto, audio_valor, ano_atual)
        if not dados.get("poster"):
            dados["poster"] = IMAGEM_PADRAO
        if not dados.get("backdrop"):
            dados["backdrop"] = dados.get("poster") or IMAGEM_PADRAO
        return dados

    def _montar_embed_preview(self, dados: dict, audio_valor: str, labels: list[str]) -> discord.Embed:
        titulo = dados["titulo"]
        sinopse = dados.get("sinopse") or ""
        descricao = (sinopse[:300] + "…") if len(sinopse) > 300 else sinopse

        embed = discord.Embed(title=titulo, description=descricao, color=COR_PRIMARIA)
        if dados.get("poster"):
            embed.set_thumbnail(url=dados["poster"])

        embed.add_field(name="Ano", value=dados.get("ano") or "—", inline=True)
        embed.add_field(name="Duração", value=dados.get("dur") or "—", inline=True)
        embed.add_field(name="Nota TMDB", value=f"★ {dados['nota']}" if dados.get("nota") else "—", inline=True)
        embed.add_field(name="Gêneros", value=", ".join(dados.get("generos_pt", [])) or "—", inline=True)
        embed.add_field(name="Áudio", value=audio_valor, inline=True)
        embed.add_field(name="Badge", value=dados.get("badge", "—"), inline=True)

        extra = dados.get("extra", {})
        if extra.get("imdb_nota"):
            embed.add_field(name="Nota IMDb", value=f"★ {extra['imdb_nota']}", inline=True)
        if extra.get("rotten_tomatoes"):
            embed.add_field(name="Rotten Tomatoes", value=extra["rotten_tomatoes"], inline=True)
        if extra.get("metascore"):
            embed.add_field(name="Metascore", value=extra["metascore"], inline=True)
        if extra.get("classificacao"):
            embed.add_field(name="Classificação", value=extra["classificacao"], inline=True)
        if extra.get("bilheteria"):
            embed.add_field(name="Bilheteria", value=extra["bilheteria"], inline=True)
        if extra.get("premios"):
            premios_texto = extra["premios"]
            embed.add_field(
                name="Prêmios",
                value=(premios_texto[:200] + "…") if len(premios_texto) > 200 else premios_texto,
                inline=False,
            )

        embed.add_field(name="Marcadores que serão adicionados", value=" · ".join(labels) or "—", inline=False)
        embed.set_footer(text="Confira as informações e clique em Confirmar para postar no Blogger.")
        return embed

    async def _publicar_no_blogger(self, mensagem: discord.Message, dados: dict, mp4: str, audio_valor: str, labels: list[str]):
        await self._editar_seguro(mensagem, content="Postando no Blogger...", embed=None, view=None)

        token = await obter_token_acesso()
        if not token:
            await self._editar_seguro(mensagem, content="Sem autorização. Use `/autorizar` e tente novamente.")
            return

        try:
            html_pagina = gerar_html_pagina_filme(
                titulo=dados["titulo"],
                video_url=mp4,
                poster_url=dados.get("poster"),
                backdrop_url=dados.get("backdrop"),
                ano=dados.get("ano"),
                nota=dados.get("nota"),
                dur=dados.get("dur"),
                generos_pt=dados.get("generos_pt", []),
                audio=audio_valor,
                sinopse=dados.get("sinopse"),
                badge=dados.get("badge"),
                tmdb_link=dados.get("tmdb_link"),
                imdb_link=dados.get("imdb_link"),
                extra=dados.get("extra", {}),
            )
        except Exception:
            logger.exception("Erro ao gerar HTML da página do filme")
            await self._editar_seguro(mensagem, content="Erro ao gerar a página do filme.")
            return

        post_url, post_id = await postar_no_blogger(token, dados["titulo"], html_pagina, labels)

        if not post_url:
            await self._editar_seguro(mensagem, content="Erro ao postar no Blogger. Verifique o token com `/autorizar`.")
            return

        embed_final = discord.Embed(
            title=dados["titulo"], description="Postado com sucesso!", color=COR_SUCESSO, url=post_url
        )
        if dados.get("poster"):
            embed_final.set_thumbnail(url=dados["poster"])

        embed_final.add_field(name="Ano", value=dados.get("ano") or "—", inline=True)
        embed_final.add_field(name="Duração", value=dados.get("dur") or "—", inline=True)
        embed_final.add_field(name="Nota TMDB", value=f"★ {dados['nota']}" if dados.get("nota") else "—", inline=True)

        extra = dados.get("extra", {})
        if extra.get("imdb_nota"):
            embed_final.add_field(name="Nota IMDb", value=f"★ {extra['imdb_nota']}", inline=True)

        embed_final.add_field(name="Gêneros", value=", ".join(dados.get("generos_pt", [])) or "—", inline=True)
        embed_final.add_field(name="Áudio", value=audio_valor, inline=True)
        embed_final.add_field(name="Link", value=f"[Ver post]({post_url})", inline=False)
        embed_final.add_field(name="Marcadores", value=" · ".join(labels), inline=False)
        embed_final.set_footer(text=f"CineTrigger Bot • ID: {post_id}")

        await self._editar_seguro(mensagem, content=None, embed=embed_final, view=None)

    @staticmethod
    async def _editar_seguro(mensagem: discord.Message, **kwargs):
        try:
            await mensagem.edit(**kwargs)
        except discord.HTTPException:
            logger.exception("Falha ao editar mensagem")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        from core.permissions import SemPermissaoError, embed_sem_permissao

        if isinstance(error, SemPermissaoError):
            embed = embed_sem_permissao(str(error))
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        logger.exception("Erro não tratado em comando de filme", exc_info=error)
        embed = discord.Embed(title="Erro", description="Ocorreu um erro inesperado.", color=COR_ERRO)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(FilmeCog(bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 8 — UTILITÁRIOS DE TICKETS (transcript e permissões de canal)
# ══════════════════════════════════════════════════════════════════

async def gerar_transcript_html(canal: discord.TextChannel, dados_ticket: dict) -> str:
    """Gera um HTML autocontido com todas as mensagens do ticket, autores, horários e anexos."""
    mensagens = []
    async for mensagem in canal.history(limit=None, oldest_first=True):
        mensagens.append(mensagem)

    linhas_html = []
    for mensagem in mensagens:
        autor = htmllib.escape(str(mensagem.author.display_name))
        avatar = mensagem.author.display_avatar.url if mensagem.author.display_avatar else ""
        horario = mensagem.created_at.strftime("%d/%m/%Y %H:%M:%S")
        conteudo = htmllib.escape(mensagem.content) if mensagem.content else ""
        conteudo = conteudo.replace("\n", "<br>")

        anexos_html = ""
        for anexo in mensagem.attachments:
            url_escapada = htmllib.escape(anexo.url)
            nome_escapado = htmllib.escape(anexo.filename)
            if anexo.content_type and anexo.content_type.startswith("image/"):
                anexos_html += (
                    f'<div class="anexo"><img src="{url_escapada}" alt="{nome_escapado}" '
                    f'style="max-width:380px;border-radius:8px;margin-top:6px"></div>'
                )
            else:
                anexos_html += (
                    f'<div class="anexo"><a href="{url_escapada}" target="_blank">{nome_escapado}</a></div>'
                )

        embeds_html = ""
        for embed in mensagem.embeds:
            titulo_embed = htmllib.escape(embed.title) if embed.title else ""
            descricao_embed = htmllib.escape(embed.description) if embed.description else ""
            if titulo_embed or descricao_embed:
                embeds_html += (
                    f'<div class="embed-box">'
                    f'{f"<div class=\"embed-titulo\">{titulo_embed}</div>" if titulo_embed else ""}'
                    f'{f"<div class=\"embed-desc\">{descricao_embed}</div>" if descricao_embed else ""}'
                    f'</div>'
                )

        linhas_html.append(f"""
        <div class="mensagem">
          <img class="avatar" src="{avatar}" alt="{autor}">
          <div class="conteudo-msg">
            <div class="cabecalho-msg">
              <span class="autor">{autor}</span>
              <span class="horario">{horario}</span>
            </div>
            <div class="texto-msg">{conteudo}</div>
            {anexos_html}
            {embeds_html}
          </div>
        </div>
        """)

    corpo_mensagens = "".join(linhas_html) if linhas_html else '<p class="vazio">Nenhuma mensagem foi enviada neste ticket.</p>'

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Transcript — {htmllib.escape(canal.name)}</title>
<style>
body{{background:#0A0A0A;color:#EEEEF5;font-family:Arial,sans-serif;margin:0;padding:24px}}
.cabecalho{{border-bottom:2px solid #E63946;padding-bottom:16px;margin-bottom:20px}}
.cabecalho h1{{margin:0 0 6px;color:#E63946}}
.info-ticket{{color:#9898B0;font-size:13px}}
.mensagem{{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #1C1C1C}}
.avatar{{width:40px;height:40px;border-radius:50%;flex-shrink:0}}
.cabecalho-msg{{display:flex;gap:10px;align-items:baseline}}
.autor{{font-weight:bold;color:#fff}}
.horario{{font-size:11px;color:#9898B0}}
.texto-msg{{margin-top:4px;line-height:1.5;white-space:pre-wrap;word-break:break-word}}
.embed-box{{border-left:3px solid #E63946;background:#1C1C1C;padding:10px 14px;border-radius:6px;margin-top:8px;max-width:480px}}
.embed-titulo{{font-weight:bold;margin-bottom:4px}}
.vazio{{color:#9898B0;text-align:center;padding:40px 0}}
</style>
</head>
<body>
<div class="cabecalho">
  <h1>{NOME_MARCA} — Transcript de Ticket</h1>
  <div class="info-ticket">
    Canal: #{htmllib.escape(canal.name)} &nbsp;|&nbsp;
    Aberto por: {htmllib.escape(dados_ticket.get("usuario_nome", "desconhecido"))} &nbsp;|&nbsp;
    Tipo: {htmllib.escape(dados_ticket.get("tipo_nome", "—"))} &nbsp;|&nbsp;
    Gerado em: {datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
  </div>
</div>
{corpo_mensagens}
</body>
</html>"""


def montar_overwrites_ticket(
    guild: discord.Guild,
    usuario: discord.Member,
    cargos_suporte_ids: list[int],
) -> dict:
    """Monta o dicionário de permissões do canal do ticket."""
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        usuario: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
        ),
    }

    for cargo_id in cargos_suporte_ids:
        cargo = guild.get_role(cargo_id)
        if cargo is not None:
            overwrites[cargo] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, attach_files=True
            )

    return overwrites


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 9 — VIEWS DO SISTEMA DE TICKETS (botões, select menus, modais)
# ══════════════════════════════════════════════════════════════════

class PainelAberturaView(discord.ui.View):
    """View persistente com o botão 'Abrir Ticket' fixado na mensagem principal."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🎫",
        custom_id="cinetrigger:ticket:abrir_painel",
    )
    async def abrir_painel(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            config_tickets = config["tickets"]

            if not config_tickets["ativo"]:
                await interaction.response.send_message(
                    embed=embed_erro("Tickets desativados", "O sistema de tickets está desativado no momento."),
                    ephemeral=True,
                )
                return

            limite = config_tickets.get("max_tickets_por_usuario", 1)
            total_abertos = await gerenciador_dados.contar_tickets_abertos_usuario(
                interaction.guild_id, interaction.user.id
            )
            if total_abertos >= limite:
                await interaction.response.send_message(
                    embed=embed_erro(
                        "Limite atingido",
                        f"Você já possui {total_abertos} ticket(s) aberto(s). O limite é {limite}.",
                    ),
                    ephemeral=True,
                )
                return

            view_selecao = SelecaoTipoTicketView(config_tickets)
            embed = embed_base(
                titulo="Selecione o tipo de ticket",
                descricao="Escolha abaixo a categoria que melhor descreve o motivo do seu ticket.",
                identidade=config.get("identidade", {}),
            )
            await interaction.response.send_message(embed=embed, view=view_selecao, ephemeral=True)
        except Exception:
            logger.exception("Erro ao abrir seleção de ticket")
            await self._responder_erro(interaction)

    @staticmethod
    async def _responder_erro(interaction: discord.Interaction):
        embed = embed_erro("Erro", "Ocorreu um erro inesperado. Tente novamente em instantes.")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


class SelecaoTipoTicketView(discord.ui.View):
    """Select menu ephemeral para o usuário escolher o tipo de ticket e criá-lo imediatamente."""

    def __init__(self, config_tickets: dict):
        super().__init__(timeout=120)
        self.config_tickets = config_tickets

        opcoes = []
        for chave, dados_tipo in config_tickets.get("tipos", {}).items():
            opcoes.append(
                discord.SelectOption(
                    label=dados_tipo.get("nome", chave)[:100],
                    value=chave,
                    emoji=dados_tipo.get("emoji") or None,
                )
            )

        select = discord.ui.Select(
            placeholder="Selecione o tipo de ticket...",
            options=opcoes[:25],
            custom_id="cinetrigger:ticket:select_tipo",
        )
        select.callback = self._callback_selecionar
        self.add_item(select)

    async def _callback_selecionar(self, interaction: discord.Interaction):
        try:
            tipo_id = interaction.data["values"][0]
            await interaction.response.defer(ephemeral=True, thinking=True)
            await criar_ticket(interaction, tipo_id)
        except Exception:
            logger.exception("Erro ao criar ticket a partir da seleção")
            embed = embed_erro("Erro", "Não foi possível criar o ticket. Tente novamente.")
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException:
                pass


async def criar_ticket(interaction: discord.Interaction, tipo_id: str):
    """Cria o canal do ticket, aplica permissões e envia a embed inicial com os botões de controle."""
    guild = interaction.guild
    usuario = interaction.user

    config = await gerenciador_dados.obter_config_guild(guild.id)
    config_tickets = config["tickets"]

    if not config_tickets["ativo"]:
        await interaction.followup.send(
            embed=embed_erro("Tickets desativados", "O sistema de tickets está desativado."), ephemeral=True
        )
        return

    categoria_id = config_tickets.get("categoria_id")
    categoria = guild.get_channel(categoria_id) if categoria_id else None
    if categoria is None or not isinstance(categoria, discord.CategoryChannel):
        await interaction.followup.send(
            embed=embed_erro(
                "Categoria não configurada",
                "A categoria de tickets ainda não foi configurada. Peça a um administrador para configurar em `/tickets categoria`.",
            ),
            ephemeral=True,
        )
        return

    tipo_dados = config_tickets.get("tipos", {}).get(tipo_id)
    if not tipo_dados:
        await interaction.followup.send(embed=embed_erro("Tipo inválido", "Este tipo de ticket não existe mais."), ephemeral=True)
        return

    cargos_suporte_ids = config_tickets.get("cargos_suporte", [])
    overwrites = montar_overwrites_ticket(guild, usuario, cargos_suporte_ids)

    novo_numero = config_tickets.get("contador", 0) + 1
    nome_canal = f"ticket-{novo_numero:04d}-{usuario.name}"[:95]

    try:
        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            topic=f"Ticket de {usuario} | Tipo: {tipo_dados.get('nome')} | ID: {novo_numero}",
            reason=f"Ticket aberto por {usuario} ({usuario.id})",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=embed_erro("Sem permissão", "Não tenho permissão para criar canais nesta categoria."),
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        logger.exception("Erro ao criar canal de ticket")
        await interaction.followup.send(
            embed=embed_erro("Erro", "Não foi possível criar o canal do ticket."), ephemeral=True
        )
        return

    await gerenciador_dados.atualizar_config_guild(guild.id, ["tickets", "contador"], novo_numero)

    dados_ticket = {
        "numero": novo_numero,
        "usuario_id": usuario.id,
        "usuario_nome": str(usuario),
        "tipo_id": tipo_id,
        "tipo_nome": tipo_dados.get("nome"),
        "status": "aberto",
        "assumido_por_id": None,
        "criado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    await gerenciador_dados.salvar_ticket(guild.id, canal.id, dados_ticket)

    identidade = config.get("identidade", {})
    embed_ticket = embed_base(
        titulo=f"Ticket #{novo_numero:04d} — {tipo_dados.get('nome')}",
        descricao="Nossa equipe foi notificada e responderá em breve. Descreva seu caso com detalhes.",
        cor_hex=config_tickets.get("cor_embed"),
        identidade=identidade,
    )
    embed_ticket.add_field(name="Aberto por", value=usuario.mention, inline=True)
    embed_ticket.add_field(name="Tipo", value=tipo_dados.get("nome"), inline=True)
    embed_ticket.add_field(name="Número", value=f"#{novo_numero:04d}", inline=True)
    embed_ticket.add_field(
        name="Data e hora",
        value=discord.utils.format_dt(datetime.datetime.now(datetime.timezone.utc), style="F"),
        inline=False,
    )

    mencoes_cargos = " ".join(
        guild.get_role(cargo_id).mention for cargo_id in cargos_suporte_ids if guild.get_role(cargo_id)
    )
    conteudo_mencao = f"{usuario.mention} {mencoes_cargos}".strip()

    view_controle = ControleTicketView()
    try:
        await canal.send(content=conteudo_mencao or usuario.mention, embed=embed_ticket, view=view_controle)
    except discord.HTTPException:
        logger.exception("Erro ao enviar mensagem inicial do ticket")

    await registrar_log(guild, config, "Ticket criado", usuario, canal, tipo_dados.get("nome"))

    embed_confirmacao = embed_sucesso("Ticket criado", f"Seu ticket foi criado em {canal.mention}.")
    await interaction.followup.send(embed=embed_confirmacao, ephemeral=True)


async def registrar_log(
    guild: discord.Guild,
    config: dict,
    acao: str,
    usuario: discord.abc.User,
    canal: discord.TextChannel | None,
    detalhe: str = "",
    arquivo: discord.File | None = None,
):
    canal_logs_id = config["tickets"].get("canal_logs_id")
    if not canal_logs_id:
        return

    canal_logs = guild.get_channel(canal_logs_id)
    if canal_logs is None:
        return

    identidade = config.get("identidade", {})
    embed = embed_base(titulo=acao, cor_hex=config["tickets"].get("cor_embed"), identidade=identidade)
    embed.add_field(name="Usuário", value=f"{usuario.mention} ({usuario})", inline=True)
    if canal is not None:
        embed.add_field(name="Canal", value=canal.mention if isinstance(canal, discord.TextChannel) else canal.name, inline=True)
    if detalhe:
        embed.add_field(name="Detalhes", value=detalhe, inline=False)

    try:
        if arquivo is not None:
            await canal_logs.send(embed=embed, file=arquivo)
        else:
            await canal_logs.send(embed=embed)
    except discord.HTTPException:
        logger.exception("Erro ao registrar log de ticket")


class ControleTicketView(discord.ui.View):
    """Botões de controle dentro do canal do ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _obter_contexto(self, interaction: discord.Interaction):
        config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
        dados_ticket = await gerenciador_dados.obter_ticket(interaction.guild_id, interaction.channel_id)
        return config, dados_ticket

    async def _verificar_staff(self, interaction: discord.Interaction, config: dict) -> bool:
        cargos_suporte = config["tickets"].get("cargos_suporte", [])
        if not isinstance(interaction.user, discord.Member):
            return False
        if await usuario_e_staff(interaction.user, cargos_suporte):
            return True
        await interaction.response.send_message(
            embed=embed_erro("Acesso negado", "Apenas a equipe de suporte pode usar este botão."), ephemeral=True
        )
        return False

    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.primary, emoji="🙋", custom_id="cinetrigger:ticket:assumir")
    async def assumir(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return

            dados_ticket["assumido_por_id"] = interaction.user.id
            await gerenciador_dados.salvar_ticket(interaction.guild_id, interaction.channel_id, dados_ticket)

            embed = embed_sucesso("Ticket assumido", f"{interaction.user.mention} assumiu este ticket.")
            await interaction.response.send_message(embed=embed)
            await registrar_log(interaction.guild, config, "Ticket assumido", interaction.user, interaction.channel)
        except Exception:
            logger.exception("Erro ao assumir ticket")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Adicionar Membro", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="cinetrigger:ticket:add_membro")
    async def adicionar_membro(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return
            await interaction.response.send_modal(ModalGerenciarMembro(acao="adicionar"))
        except Exception:
            logger.exception("Erro ao abrir modal de adicionar membro")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Remover Membro", style=discord.ButtonStyle.secondary, emoji="➖", custom_id="cinetrigger:ticket:remover_membro")
    async def remover_membro(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return
            await interaction.response.send_modal(ModalGerenciarMembro(acao="remover"))
        except Exception:
            logger.exception("Erro ao abrir modal de remover membro")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Renomear", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="cinetrigger:ticket:renomear")
    async def renomear(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return
            await interaction.response.send_modal(ModalRenomearTicket())
        except Exception:
            logger.exception("Erro ao abrir modal de renomear ticket")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="cinetrigger:ticket:fechar")
    async def fechar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return

            view_confirmacao = ConfirmarFecharView(dados_ticket)
            embed = embed_base(
                titulo="Confirmar fechamento",
                descricao="Tem certeza que deseja fechar este ticket? O canal será bloqueado para o usuário.",
                identidade=config.get("identidade", {}),
            )
            await interaction.response.send_message(embed=embed, view=view_confirmacao)
        except Exception:
            logger.exception("Erro ao solicitar fechamento de ticket")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Reabrir", style=discord.ButtonStyle.success, emoji="🔓", custom_id="cinetrigger:ticket:reabrir")
    async def reabrir(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return

            if dados_ticket.get("status") != "fechado":
                await interaction.response.send_message(
                    embed=embed_erro("Ação inválida", "Este ticket não está fechado."), ephemeral=True
                )
                return

            usuario_id = dados_ticket.get("usuario_id")
            usuario_membro = interaction.guild.get_member(usuario_id)
            if usuario_membro is not None:
                await interaction.channel.set_permissions(
                    usuario_membro, view_channel=True, send_messages=True, read_message_history=True
                )

            dados_ticket["status"] = "aberto"
            await gerenciador_dados.salvar_ticket(interaction.guild_id, interaction.channel_id, dados_ticket)

            embed = embed_sucesso("Ticket reaberto", f"{interaction.user.mention} reabriu este ticket.")
            await interaction.response.send_message(embed=embed)
            await registrar_log(interaction.guild, config, "Ticket reaberto", interaction.user, interaction.channel)
        except Exception:
            logger.exception("Erro ao reabrir ticket")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Excluir", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="cinetrigger:ticket:excluir")
    async def excluir(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return

            view_confirmacao = ConfirmarExcluirView()
            embed = embed_base(
                titulo="Confirmar exclusão",
                descricao="Esta ação é irreversível. O canal será excluído permanentemente em 5 segundos após a confirmação.",
                identidade=config.get("identidade", {}),
            )
            await interaction.response.send_message(embed=embed, view=view_confirmacao)
        except Exception:
            logger.exception("Erro ao solicitar exclusão de ticket")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📄", custom_id="cinetrigger:ticket:transcript")
    async def gerar_transcript_botao(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            html_transcript = await gerar_transcript_html(interaction.channel, dados_ticket)
            arquivo = discord.File(
                io.BytesIO(html_transcript.encode("utf-8")), filename=f"transcript-{dados_ticket.get('numero', 0):04d}.html"
            )
            await interaction.followup.send("Transcript gerada.", file=arquivo, ephemeral=True)

            arquivo_log = discord.File(
                io.BytesIO(html_transcript.encode("utf-8")), filename=f"transcript-{dados_ticket.get('numero', 0):04d}.html"
            )
            await registrar_log(
                interaction.guild, config, "Transcript enviada", interaction.user, interaction.channel, arquivo=arquivo_log
            )
        except Exception:
            logger.exception("Erro ao gerar transcript")
            await self._responder_erro(interaction)

    @discord.ui.button(label="Transferir", style=discord.ButtonStyle.secondary, emoji="🔀", custom_id="cinetrigger:ticket:transferir")
    async def transferir(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            config, dados_ticket = await self._obter_contexto(interaction)
            if dados_ticket is None:
                await interaction.response.send_message(embed=embed_erro("Erro", "Ticket não encontrado."), ephemeral=True)
                return
            if not await self._verificar_staff(interaction, config):
                return

            categorias = [c for c in interaction.guild.categories]
            if not categorias:
                await interaction.response.send_message(
                    embed=embed_erro("Sem categorias", "Não há categorias disponíveis no servidor."), ephemeral=True
                )
                return

            view_selecao = SelecaoCategoriaTransferenciaView(categorias)
            await interaction.response.send_message(
                embed=embed_base(titulo="Transferir ticket", descricao="Selecione a categoria de destino."),
                view=view_selecao,
                ephemeral=True,
            )
        except Exception:
            logger.exception("Erro ao iniciar transferência de ticket")
            await self._responder_erro(interaction)

    @staticmethod
    async def _responder_erro(interaction: discord.Interaction):
        embed = embed_erro("Erro", "Ocorreu um erro inesperado. Tente novamente.")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


class ModalGerenciarMembro(discord.ui.Modal):
    def __init__(self, acao: str):
        titulo = "Adicionar membro ao ticket" if acao == "adicionar" else "Remover membro do ticket"
        super().__init__(title=titulo)
        self.acao = acao
        self.usuario_input = discord.ui.TextInput(
            label="ID ou menção do usuário",
            placeholder="Ex: 123456789012345678",
            required=True,
            max_length=32,
        )
        self.add_item(self.usuario_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            texto = self.usuario_input.value.strip().strip("<@!>")
            if not texto.isdigit():
                await interaction.response.send_message(
                    embed=embed_erro("Entrada inválida", "Informe um ID de usuário válido."), ephemeral=True
                )
                return

            membro = interaction.guild.get_member(int(texto))
            if membro is None:
                await interaction.response.send_message(
                    embed=embed_erro("Usuário não encontrado", "Não encontrei esse membro no servidor."), ephemeral=True
                )
                return

            if self.acao == "adicionar":
                await interaction.channel.set_permissions(
                    membro, view_channel=True, send_messages=True, read_message_history=True, attach_files=True
                )
                embed = embed_sucesso("Membro adicionado", f"{membro.mention} agora tem acesso a este ticket.")
            else:
                await interaction.channel.set_permissions(membro, overwrite=None)
                embed = embed_sucesso("Membro removido", f"{membro.mention} não tem mais acesso a este ticket.")

            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_erro("Sem permissão", "Não tenho permissão para alterar este canal."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao gerenciar membro do ticket")
            await interaction.response.send_message(
                embed=embed_erro("Erro", "Ocorreu um erro ao processar sua solicitação."), ephemeral=True
            )


class ModalRenomearTicket(discord.ui.Modal, title="Renomear ticket"):
    novo_nome = discord.ui.TextInput(label="Novo nome do canal", placeholder="Ex: ticket-suporte-joao", max_length=90)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.channel.edit(name=self.novo_nome.value)
            await interaction.response.send_message(embed=embed_sucesso("Ticket renomeado", f"Novo nome: {self.novo_nome.value}"))
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_erro("Sem permissão", "Não tenho permissão para renomear este canal."), ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=embed_erro("Erro", "Não foi possível renomear o canal. Verifique se o nome é válido."), ephemeral=True
            )


class ConfirmarFecharView(discord.ui.View):
    def __init__(self, dados_ticket: dict):
        super().__init__(timeout=60)
        self.dados_ticket = dados_ticket

    @discord.ui.button(label="Confirmar Fechamento", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            usuario_id = self.dados_ticket.get("usuario_id")
            usuario_membro = interaction.guild.get_member(usuario_id)
            if usuario_membro is not None:
                await interaction.channel.set_permissions(usuario_membro, view_channel=True, send_messages=False)

            self.dados_ticket["status"] = "fechado"
            await gerenciador_dados.salvar_ticket(interaction.guild_id, interaction.channel_id, self.dados_ticket)

            html_transcript = await gerar_transcript_html(interaction.channel, self.dados_ticket)
            arquivo = discord.File(
                io.BytesIO(html_transcript.encode("utf-8")),
                filename=f"transcript-{self.dados_ticket.get('numero', 0):04d}.html",
            )
            await registrar_log(
                interaction.guild, config, "Ticket fechado", interaction.user, interaction.channel, arquivo=arquivo
            )

            embed = embed_sucesso("Ticket fechado", "Este ticket foi fechado. Use Reabrir ou Excluir conforme necessário.")
            await interaction.followup.send(embed=embed)
        except Exception:
            logger.exception("Erro ao confirmar fechamento de ticket")

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)


class ConfirmarExcluirView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirmar Exclusão", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        try:
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)

            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            await registrar_log(interaction.guild, config, "Ticket excluído", interaction.user, interaction.channel)
            await gerenciador_dados.remover_ticket(interaction.guild_id, interaction.channel_id)

            await interaction.followup.send("Excluindo o canal em instantes...")
            await interaction.channel.delete(reason=f"Ticket excluído por {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(
                embed=embed_erro("Sem permissão", "Não tenho permissão para excluir este canal."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao excluir ticket")

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)


class SelecaoCategoriaTransferenciaView(discord.ui.View):
    def __init__(self, categorias: list[discord.CategoryChannel]):
        super().__init__(timeout=60)
        opcoes = [
            discord.SelectOption(label=categoria.name[:100], value=str(categoria.id))
            for categoria in categorias[:25]
        ]
        select = discord.ui.Select(placeholder="Selecione a categoria...", options=opcoes)
        select.callback = self._callback
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction):
        try:
            categoria_id = int(interaction.data["values"][0])
            categoria = interaction.guild.get_channel(categoria_id)
            if categoria is None or not isinstance(categoria, discord.CategoryChannel):
                await interaction.response.send_message(
                    embed=embed_erro("Erro", "Categoria não encontrada."), ephemeral=True
                )
                return

            canal_ticket = interaction.channel
            dados_ticket = await gerenciador_dados.obter_ticket(interaction.guild_id, canal_ticket.id)
            if dados_ticket is None:
                await interaction.response.send_message(
                    embed=embed_erro("Erro", "Este ticket não foi encontrado nos registros."), ephemeral=True
                )
                return

            try:
                await canal_ticket.edit(category=categoria, reason=f"Ticket transferido por {interaction.user}")
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=embed_erro("Sem permissão", "Não tenho permissão para mover este canal."), ephemeral=True
                )
                return
            except discord.HTTPException:
                logger.exception("Erro ao mover canal de ticket")
                await interaction.response.send_message(
                    embed=embed_erro("Erro", "Não foi possível mover o canal para a categoria selecionada."), ephemeral=True
                )
                return

            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            embed = embed_sucesso("Ticket transferido", f"Este ticket foi movido para a categoria **{categoria.name}**.")
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
            await canal_ticket.send(embed=embed)
            await registrar_log(
                interaction.guild, config, "Ticket transferido", interaction.user, canal_ticket, detalhe=f"Nova categoria: {categoria.name}"
            )
        except Exception:
            logger.exception("Erro ao processar seleção de categoria de transferência")
            await interaction.response.send_message(embed=embed_erro("Erro", "Erro ao transferir o ticket."), ephemeral=True)


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 10 — COG: COMANDOS ADMINISTRATIVOS DE TICKETS (/tickets ...)
# ══════════════════════════════════════════════════════════════════

class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Views persistentes precisam ser registradas para sobreviver a reinícios do bot.
        self.bot.add_view(PainelAberturaView())
        self.bot.add_view(ControleTicketView())

    grupo_tickets = app_commands.Group(
        name="tickets", description="Configuração do sistema de tickets", default_permissions=discord.Permissions(administrator=True)
    )

    @grupo_tickets.command(name="painel", description="Envia ou atualiza a mensagem principal do sistema de tickets")
    @apenas_administrador()
    @app_commands.describe(canal="Canal onde a mensagem de abertura de tickets será enviada")
    async def cmd_painel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        try:
            await interaction.response.defer(ephemeral=True)
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            config_tickets = config["tickets"]

            embed = embed_base(
                titulo=config_tickets.get("titulo_mensagem", "Central de Atendimento"),
                descricao=config_tickets.get("descricao_mensagem", "Clique no botão abaixo para abrir um ticket."),
                cor_hex=config_tickets.get("cor_embed"),
                identidade=config.get("identidade", {}),
            )

            view = PainelAberturaView()
            mensagem = await canal.send(embed=embed, view=view)

            config = await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "canal_mensagem_id"], canal.id)
            config = await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "mensagem_id"], mensagem.id)

            await interaction.followup.send(
                embed=embed_sucesso("Painel enviado", f"A mensagem de tickets foi enviada em {canal.mention}."), ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=embed_erro("Sem permissão", "Não tenho permissão para enviar mensagens nesse canal."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao enviar painel de tickets")
            await interaction.followup.send(embed=embed_erro("Erro", "Ocorreu um erro ao enviar o painel."), ephemeral=True)

    @grupo_tickets.command(name="ativar", description="Ativa ou desativa o sistema de tickets")
    @apenas_administrador()
    @app_commands.describe(estado="Ativar ou desativar o sistema")
    @app_commands.choices(estado=[
        app_commands.Choice(name="Ativar", value="ativar"),
        app_commands.Choice(name="Desativar", value="desativar"),
    ])
    async def cmd_ativar(self, interaction: discord.Interaction, estado: app_commands.Choice[str]):
        try:
            novo_valor = estado.value == "ativar"
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "ativo"], novo_valor)
            texto = "ativado" if novo_valor else "desativado"
            await interaction.response.send_message(
                embed=embed_sucesso("Configuração salva", f"O sistema de tickets foi **{texto}**."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao ativar/desativar tickets")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="categoria", description="Define a categoria onde os tickets serão criados")
    @apenas_administrador()
    @app_commands.describe(categoria="Categoria de destino dos tickets")
    async def cmd_categoria(self, interaction: discord.Interaction, categoria: discord.CategoryChannel):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "categoria_id"], categoria.id)
            await interaction.response.send_message(
                embed=embed_sucesso("Categoria definida", f"Os tickets serão criados em **{categoria.name}**."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao definir categoria de tickets")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="logs", description="Define o canal de logs do sistema de tickets")
    @apenas_administrador()
    @app_commands.describe(canal="Canal onde os logs de tickets serão enviados")
    async def cmd_logs(self, interaction: discord.Interaction, canal: discord.TextChannel):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "canal_logs_id"], canal.id)
            await interaction.response.send_message(
                embed=embed_sucesso("Canal de logs definido", f"Os logs de tickets serão enviados em {canal.mention}."),
                ephemeral=True,
            )
        except Exception:
            logger.exception("Erro ao definir canal de logs")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="limite", description="Define o número máximo de tickets abertos por usuário")
    @apenas_administrador()
    @app_commands.describe(quantidade="Número máximo de tickets simultâneos por usuário (1 a 10)")
    async def cmd_limite(self, interaction: discord.Interaction, quantidade: app_commands.Range[int, 1, 10]):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "max_tickets_por_usuario"], quantidade)
            await interaction.response.send_message(
                embed=embed_sucesso("Limite atualizado", f"Cada usuário poderá abrir até **{quantidade}** ticket(s) simultâneos."),
                ephemeral=True,
            )
        except Exception:
            logger.exception("Erro ao definir limite de tickets")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="cargo-adicionar", description="Adiciona um cargo de suporte com acesso a todos os tickets")
    @apenas_administrador()
    @app_commands.describe(cargo="Cargo que terá acesso automático a todos os tickets")
    async def cmd_cargo_adicionar(self, interaction: discord.Interaction, cargo: discord.Role):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            cargos = config["tickets"].get("cargos_suporte", [])
            if cargo.id in cargos:
                await interaction.response.send_message(
                    embed=embed_erro("Já adicionado", f"O cargo {cargo.mention} já é um cargo de suporte."), ephemeral=True
                )
                return

            cargos.append(cargo.id)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "cargos_suporte"], cargos)
            await interaction.response.send_message(
                embed=embed_sucesso("Cargo adicionado", f"{cargo.mention} agora tem acesso a todos os tickets."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao adicionar cargo de suporte")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="cargo-remover", description="Remove um cargo de suporte do sistema de tickets")
    @apenas_administrador()
    @app_commands.describe(cargo="Cargo a ser removido da lista de cargos de suporte")
    async def cmd_cargo_remover(self, interaction: discord.Interaction, cargo: discord.Role):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            cargos = config["tickets"].get("cargos_suporte", [])
            if cargo.id not in cargos:
                await interaction.response.send_message(
                    embed=embed_erro("Não encontrado", f"O cargo {cargo.mention} não está na lista de suporte."), ephemeral=True
                )
                return

            cargos.remove(cargo.id)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "cargos_suporte"], cargos)
            await interaction.response.send_message(
                embed=embed_sucesso("Cargo removido", f"{cargo.mention} não tem mais acesso automático aos tickets."),
                ephemeral=True,
            )
        except Exception:
            logger.exception("Erro ao remover cargo de suporte")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="cargos-listar", description="Lista os cargos de suporte configurados")
    @apenas_administrador()
    async def cmd_cargos_listar(self, interaction: discord.Interaction):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            cargos_ids = config["tickets"].get("cargos_suporte", [])

            if not cargos_ids:
                await interaction.response.send_message(
                    embed=embed_erro("Nenhum cargo configurado", "Use `/tickets cargo-adicionar` para adicionar cargos de suporte."),
                    ephemeral=True,
                )
                return

            mencoes = []
            for cargo_id in cargos_ids:
                cargo = interaction.guild.get_role(cargo_id)
                mencoes.append(cargo.mention if cargo else f"Cargo removido (ID: {cargo_id})")

            embed = embed_base(titulo="Cargos de suporte", descricao="\n".join(mencoes))
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Erro ao listar cargos de suporte")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível listar os cargos."), ephemeral=True)

    @grupo_tickets.command(name="aparencia", description="Personaliza a cor, logo, thumbnail e rodapé das embeds de tickets")
    @apenas_administrador()
    @app_commands.describe(
        cor="Cor em hexadecimal (ex: #E63946)",
        logo_url="URL da imagem usada como logo",
        thumbnail_url="URL da imagem usada como thumbnail",
        rodape="Texto do rodapé das embeds",
    )
    async def cmd_aparencia(
        self,
        interaction: discord.Interaction,
        cor: str = None,
        logo_url: str = None,
        thumbnail_url: str = None,
        rodape: str = None,
    ):
        try:
            alteracoes = []

            if cor is not None:
                cor_normalizada = cor if cor.startswith("#") else f"#{cor}"
                try:
                    int(cor_normalizada.lstrip("#"), 16)
                except ValueError:
                    await interaction.response.send_message(
                        embed=embed_erro("Cor inválida", "Informe uma cor hexadecimal válida, ex: `#E63946`."), ephemeral=True
                    )
                    return
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["tickets", "cor_embed"], cor_normalizada)
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["identidade", "cor_padrao"], cor_normalizada)
                alteracoes.append(f"Cor: {cor_normalizada}")

            if logo_url is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["identidade", "logo_url"], logo_url)
                alteracoes.append("Logo atualizada")

            if thumbnail_url is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["identidade", "thumbnail_url"], thumbnail_url)
                alteracoes.append("Thumbnail atualizada")

            if rodape is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["identidade", "rodape"], rodape)
                alteracoes.append(f"Rodapé: {rodape}")

            if not alteracoes:
                await interaction.response.send_message(
                    embed=embed_erro("Nada para atualizar", "Informe ao menos um parâmetro para alterar."), ephemeral=True
                )
                return

            await interaction.response.send_message(
                embed=embed_sucesso("Aparência atualizada", "\n".join(alteracoes)), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao atualizar aparência dos tickets")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_tickets.command(name="status", description="Mostra a configuração atual do sistema de tickets")
    @apenas_administrador()
    async def cmd_status(self, interaction: discord.Interaction):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            config_tickets = config["tickets"]

            categoria = interaction.guild.get_channel(config_tickets.get("categoria_id")) if config_tickets.get("categoria_id") else None
            canal_logs = interaction.guild.get_channel(config_tickets.get("canal_logs_id")) if config_tickets.get("canal_logs_id") else None
            cargos = [interaction.guild.get_role(cid) for cid in config_tickets.get("cargos_suporte", [])]
            cargos_texto = ", ".join(c.mention for c in cargos if c) or "Nenhum"

            embed = embed_base(titulo="Status do sistema de tickets", identidade=config.get("identidade", {}))
            embed.add_field(name="Ativo", value="Sim" if config_tickets.get("ativo") else "Não", inline=True)
            embed.add_field(name="Categoria", value=categoria.name if categoria else "Não configurada", inline=True)
            embed.add_field(name="Canal de logs", value=canal_logs.mention if canal_logs else "Não configurado", inline=True)
            embed.add_field(name="Limite por usuário", value=str(config_tickets.get("max_tickets_por_usuario", 1)), inline=True)
            embed.add_field(name="Tickets já criados", value=str(config_tickets.get("contador", 0)), inline=True)
            embed.add_field(name="Cargos de suporte", value=cargos_texto, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Erro ao exibir status de tickets")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível carregar o status."), ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canal: discord.abc.GuildChannel):
        """Remove o registro de um ticket caso o canal seja excluído manualmente."""
        if not isinstance(canal, discord.TextChannel):
            return
        try:
            await gerenciador_dados.remover_ticket(canal.guild.id, canal.id)
        except Exception:
            logger.exception("Erro ao limpar registro de ticket após exclusão de canal")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, SemPermissaoError):
            embed = embed_sem_permissao(str(error))
        else:
            logger.exception("Erro não tratado em comando de tickets", exc_info=error)
            embed = embed_erro("Erro", "Ocorreu um erro inesperado ao executar este comando.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 11 — COG: MODERAÇÃO (Lock, Unlock, Anti-Link)
# ══════════════════════════════════════════════════════════════════

PADRAO_LINK = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)


class ModeracaoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="lock", description="Bloqueia o envio de mensagens no canal atual")
    @app_commands.default_permissions(administrator=True)
    @apenas_administrador()
    @app_commands.describe(canal="Canal a ser bloqueado (padrão: canal atual)", motivo="Motivo do bloqueio")
    async def cmd_lock(self, interaction: discord.Interaction, canal: discord.TextChannel = None, motivo: str = None):
        try:
            canal_alvo = canal or interaction.channel
            await canal_alvo.set_permissions(
                interaction.guild.default_role,
                send_messages=False,
                reason=f"Lock por {interaction.user} | Motivo: {motivo or 'não informado'}",
            )
            embed = embed_base(
                titulo="Canal bloqueado",
                descricao=f"{canal_alvo.mention} foi bloqueado para envio de mensagens.",
            )
            if motivo:
                embed.add_field(name="Motivo", value=motivo, inline=False)
            embed.add_field(name="Responsável", value=interaction.user.mention, inline=False)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_erro("Sem permissão", "Não tenho permissão para alterar este canal."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao executar /lock")
            await interaction.response.send_message(embed=embed_erro("Erro", "Ocorreu um erro ao bloquear o canal."), ephemeral=True)

    @app_commands.command(name="unlock", description="Libera o envio de mensagens no canal atual")
    @app_commands.default_permissions(administrator=True)
    @apenas_administrador()
    @app_commands.describe(canal="Canal a ser liberado (padrão: canal atual)")
    async def cmd_unlock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        try:
            canal_alvo = canal or interaction.channel
            await canal_alvo.set_permissions(
                interaction.guild.default_role, send_messages=None, reason=f"Unlock por {interaction.user}"
            )
            embed = embed_sucesso("Canal liberado", f"{canal_alvo.mention} foi liberado para envio de mensagens.")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_erro("Sem permissão", "Não tenho permissão para alterar este canal."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao executar /unlock")
            await interaction.response.send_message(embed=embed_erro("Erro", "Ocorreu um erro ao liberar o canal."), ephemeral=True)

    grupo_antilink = app_commands.Group(
        name="antilink", description="Configuração do sistema Anti-Link", default_permissions=discord.Permissions(administrator=True)
    )

    @grupo_antilink.command(name="ativar", description="Ativa ou desativa o Anti-Link")
    @apenas_administrador()
    @app_commands.choices(estado=[
        app_commands.Choice(name="Ativar", value="ativar"),
        app_commands.Choice(name="Desativar", value="desativar"),
    ])
    async def cmd_antilink_ativar(self, interaction: discord.Interaction, estado: app_commands.Choice[str]):
        try:
            novo_valor = estado.value == "ativar"
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["moderacao", "anti_link_ativo"], novo_valor)
            texto = "ativado" if novo_valor else "desativado"
            await interaction.response.send_message(embed=embed_sucesso("Anti-Link atualizado", f"O Anti-Link foi **{texto}**."), ephemeral=True)
        except Exception:
            logger.exception("Erro ao ativar/desativar anti-link")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_antilink.command(name="ignorar-canal", description="Ignora um canal na verificação do Anti-Link")
    @apenas_administrador()
    async def cmd_antilink_ignorar_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            canais = config["moderacao"].get("anti_link_canais_ignorados", [])
            if canal.id in canais:
                await interaction.response.send_message(
                    embed=embed_erro("Já ignorado", f"{canal.mention} já está na lista de exceções."), ephemeral=True
                )
                return
            canais.append(canal.id)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["moderacao", "anti_link_canais_ignorados"], canais)
            await interaction.response.send_message(
                embed=embed_sucesso("Canal ignorado", f"Links serão permitidos em {canal.mention}."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao adicionar canal ignorado do anti-link")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_antilink.command(name="permitir-cargo", description="Permite que um cargo envie links mesmo com o Anti-Link ativo")
    @apenas_administrador()
    async def cmd_antilink_permitir_cargo(self, interaction: discord.Interaction, cargo: discord.Role):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            cargos = config["moderacao"].get("anti_link_cargos_ignorados", [])
            if cargo.id in cargos:
                await interaction.response.send_message(
                    embed=embed_erro("Já permitido", f"{cargo.mention} já pode enviar links."), ephemeral=True
                )
                return
            cargos.append(cargo.id)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["moderacao", "anti_link_cargos_ignorados"], cargos)
            await interaction.response.send_message(
                embed=embed_sucesso("Cargo liberado", f"{cargo.mention} agora pode enviar links."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao permitir cargo no anti-link")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, mensagem: discord.Message):
        if mensagem.author.bot or mensagem.guild is None:
            return

        try:
            config = await gerenciador_dados.obter_config_guild(mensagem.guild.id)
            config_moderacao = config["moderacao"]

            if not config_moderacao.get("anti_link_ativo"):
                return

            if mensagem.channel.id in config_moderacao.get("anti_link_canais_ignorados", []):
                return

            if isinstance(mensagem.author, discord.Member):
                if mensagem.author.guild_permissions.administrator:
                    return
                ids_cargos_membro = {cargo.id for cargo in mensagem.author.roles}
                if ids_cargos_membro.intersection(set(config_moderacao.get("anti_link_cargos_ignorados", []))):
                    return

            if PADRAO_LINK.search(mensagem.content):
                try:
                    await mensagem.delete()
                except discord.Forbidden:
                    logger.warning("Sem permissão para apagar mensagem com link no anti-link")
                    return
                except discord.NotFound:
                    return

                try:
                    aviso = await mensagem.channel.send(
                        embed=embed_erro("Link não permitido", f"{mensagem.author.mention}, o envio de links não é permitido neste canal.")
                    )
                    await aviso.delete(delay=6)
                except discord.HTTPException:
                    pass
        except Exception:
            logger.exception("Erro no listener do anti-link")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, SemPermissaoError):
            embed = embed_sem_permissao(str(error))
        else:
            logger.exception("Erro não tratado em comando de moderação", exc_info=error)
            embed = embed_erro("Erro", "Ocorreu um erro inesperado ao executar este comando.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ModeracaoCog(bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 12 — COG: AUTO ROLE
# ══════════════════════════════════════════════════════════════════

class AutoRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo_autorole = app_commands.Group(
        name="autorole", description="Configuração do Auto Role", default_permissions=discord.Permissions(administrator=True)
    )

    @grupo_autorole.command(name="definir", description="Define o cargo atribuído automaticamente a novos membros")
    @apenas_administrador()
    async def cmd_definir(self, interaction: discord.Interaction, cargo: discord.Role):
        try:
            if cargo >= interaction.guild.me.top_role:
                await interaction.response.send_message(
                    embed=embed_erro(
                        "Cargo muito alto",
                        "Este cargo está acima do meu cargo mais alto. Não conseguirei atribuí-lo automaticamente.",
                    ),
                    ephemeral=True,
                )
                return

            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["autorole", "cargo_id"], cargo.id)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["autorole", "ativo"], True)
            await interaction.response.send_message(
                embed=embed_sucesso("Auto Role configurado", f"Novos membros receberão automaticamente o cargo {cargo.mention}."),
                ephemeral=True,
            )
        except Exception:
            logger.exception("Erro ao definir auto role")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_autorole.command(name="desativar", description="Desativa o Auto Role")
    @apenas_administrador()
    async def cmd_desativar(self, interaction: discord.Interaction):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["autorole", "ativo"], False)
            await interaction.response.send_message(embed=embed_sucesso("Auto Role desativado", "Novos membros não receberão mais o cargo automático."), ephemeral=True)
        except Exception:
            logger.exception("Erro ao desativar auto role")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_autorole.command(name="status", description="Mostra a configuração atual do Auto Role")
    @apenas_administrador()
    async def cmd_status(self, interaction: discord.Interaction):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            config_autorole = config["autorole"]
            cargo = interaction.guild.get_role(config_autorole.get("cargo_id")) if config_autorole.get("cargo_id") else None

            embed = embed_base(titulo="Status do Auto Role")
            embed.add_field(name="Ativo", value="Sim" if config_autorole.get("ativo") else "Não", inline=True)
            embed.add_field(name="Cargo", value=cargo.mention if cargo else "Não configurado", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Erro ao exibir status do auto role")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível carregar o status."), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        try:
            config = await gerenciador_dados.obter_config_guild(membro.guild.id)
            config_autorole = config["autorole"]

            if not config_autorole.get("ativo"):
                return

            cargo_id = config_autorole.get("cargo_id")
            if not cargo_id:
                return

            cargo = membro.guild.get_role(cargo_id)
            if cargo is None:
                return

            if cargo >= membro.guild.me.top_role:
                logger.warning("Auto Role: cargo configurado está acima do cargo do bot")
                return

            await membro.add_roles(cargo, reason="Auto Role")
        except discord.Forbidden:
            logger.warning("Sem permissão para atribuir cargo automático")
        except Exception:
            logger.exception("Erro no listener de auto role")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, SemPermissaoError):
            embed = embed_sem_permissao(str(error))
        else:
            logger.exception("Erro não tratado em comando de auto role", exc_info=error)
            embed = embed_erro("Erro", "Ocorreu um erro inesperado ao executar este comando.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleCog(bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 13 — COG: BOAS-VINDAS
# ══════════════════════════════════════════════════════════════════

def _formatar_mensagem(template: str, membro: discord.Member) -> str:
    return (
        template.replace("{membro}", membro.mention)
        .replace("{usuario}", str(membro))
        .replace("{servidor}", membro.guild.name)
        .replace("{total_membros}", str(membro.guild.member_count))
    )


class BoasVindasCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo_boasvindas = app_commands.Group(
        name="boasvindas", description="Configuração do sistema de Boas-vindas", default_permissions=discord.Permissions(administrator=True)
    )

    @grupo_boasvindas.command(name="canal", description="Define o canal onde as boas-vindas serão enviadas")
    @apenas_administrador()
    async def cmd_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "canal_id"], canal.id)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "ativo"], True)
            await interaction.response.send_message(
                embed=embed_sucesso("Canal definido", f"As boas-vindas serão enviadas em {canal.mention}."), ephemeral=True
            )
        except Exception:
            logger.exception("Erro ao definir canal de boas-vindas")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_boasvindas.command(name="desativar", description="Desativa o sistema de boas-vindas")
    @apenas_administrador()
    async def cmd_desativar(self, interaction: discord.Interaction):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "ativo"], False)
            await interaction.response.send_message(embed=embed_sucesso("Boas-vindas desativadas", "O sistema de boas-vindas foi desativado."), ephemeral=True)
        except Exception:
            logger.exception("Erro ao desativar boas-vindas")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_boasvindas.command(name="mensagem", description="Define o título e o texto da mensagem de boas-vindas")
    @apenas_administrador()
    @app_commands.describe(
        titulo="Título da embed de boas-vindas",
        mensagem="Texto da mensagem. Use {membro}, {usuario}, {servidor} e {total_membros}",
    )
    async def cmd_mensagem(self, interaction: discord.Interaction, titulo: str, mensagem: str):
        try:
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "titulo"], titulo)
            await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "mensagem"], mensagem)
            await interaction.response.send_message(embed=embed_sucesso("Mensagem atualizada", "A mensagem de boas-vindas foi salva."), ephemeral=True)
        except Exception:
            logger.exception("Erro ao definir mensagem de boas-vindas")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_boasvindas.command(name="aparencia", description="Personaliza cor, banner e thumbnail das boas-vindas")
    @apenas_administrador()
    @app_commands.describe(
        cor="Cor em hexadecimal (ex: #E63946)",
        banner_url="URL da imagem grande exibida na embed",
        thumbnail_url="URL da imagem pequena exibida no canto",
        mostrar_avatar="Se o avatar do membro deve aparecer como thumbnail",
    )
    async def cmd_aparencia(
        self,
        interaction: discord.Interaction,
        cor: str = None,
        banner_url: str = None,
        thumbnail_url: str = None,
        mostrar_avatar: bool = None,
    ):
        try:
            alteracoes = []

            if cor is not None:
                cor_normalizada = cor if cor.startswith("#") else f"#{cor}"
                try:
                    int(cor_normalizada.lstrip("#"), 16)
                except ValueError:
                    await interaction.response.send_message(
                        embed=embed_erro("Cor inválida", "Informe uma cor hexadecimal válida, ex: `#E63946`."), ephemeral=True
                    )
                    return
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "cor_embed"], cor_normalizada)
                alteracoes.append(f"Cor: {cor_normalizada}")

            if banner_url is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "imagem_banner_url"], banner_url)
                alteracoes.append("Banner atualizado")

            if thumbnail_url is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "thumbnail_url"], thumbnail_url)
                alteracoes.append("Thumbnail atualizada")

            if mostrar_avatar is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["boas_vindas", "mostrar_avatar"], mostrar_avatar)
                alteracoes.append(f"Mostrar avatar: {'Sim' if mostrar_avatar else 'Não'}")

            if not alteracoes:
                await interaction.response.send_message(
                    embed=embed_erro("Nada para atualizar", "Informe ao menos um parâmetro para alterar."), ephemeral=True
                )
                return

            await interaction.response.send_message(embed=embed_sucesso("Aparência atualizada", "\n".join(alteracoes)), ephemeral=True)
        except Exception:
            logger.exception("Erro ao atualizar aparência de boas-vindas")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    @grupo_boasvindas.command(name="testar", description="Envia uma prévia da mensagem de boas-vindas no canal atual")
    @apenas_administrador()
    async def cmd_testar(self, interaction: discord.Interaction):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            embed = self._montar_embed_boas_vindas(config["boas_vindas"], interaction.user)
            await interaction.response.send_message(content="Prévia da mensagem de boas-vindas:", embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Erro ao testar boas-vindas")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível gerar a prévia."), ephemeral=True)

    @staticmethod
    def _montar_embed_boas_vindas(config_bv: dict, membro: discord.Member) -> discord.Embed:
        titulo = config_bv.get("titulo", "Bem-vindo(a)!")
        mensagem = _formatar_mensagem(config_bv.get("mensagem", ""), membro)

        embed = embed_base(titulo=titulo, descricao=mensagem, cor_hex=config_bv.get("cor_embed"))

        if config_bv.get("mostrar_avatar", True):
            embed.set_thumbnail(url=membro.display_avatar.url)
        elif config_bv.get("thumbnail_url"):
            embed.set_thumbnail(url=config_bv["thumbnail_url"])

        if config_bv.get("imagem_banner_url"):
            embed.set_image(url=config_bv["imagem_banner_url"])

        return embed

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        try:
            config = await gerenciador_dados.obter_config_guild(membro.guild.id)
            config_bv = config["boas_vindas"]

            if not config_bv.get("ativo"):
                return

            canal_id = config_bv.get("canal_id")
            if not canal_id:
                return

            canal = membro.guild.get_channel(canal_id)
            if canal is None:
                return

            embed = self._montar_embed_boas_vindas(config_bv, membro)
            await canal.send(content=membro.mention, embed=embed)
        except discord.Forbidden:
            logger.warning("Sem permissão para enviar mensagem de boas-vindas")
        except Exception:
            logger.exception("Erro no listener de boas-vindas")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, SemPermissaoError):
            embed = embed_sem_permissao(str(error))
        else:
            logger.exception("Erro não tratado em comando de boas-vindas", exc_info=error)
            embed = embed_erro("Erro", "Ocorreu um erro inesperado ao executar este comando.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasCog(bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 14 — COG: ANÚNCIOS
# ══════════════════════════════════════════════════════════════════

class ModalAnuncio(discord.ui.Modal, title="Criar anúncio"):
    titulo_anuncio = discord.ui.TextInput(label="Título", max_length=256, required=True)
    descricao_anuncio = discord.ui.TextInput(
        label="Mensagem", style=discord.TextStyle.paragraph, max_length=4000, required=True
    )
    imagem_url = discord.ui.TextInput(label="URL da imagem (opcional)", required=False, max_length=500)

    def __init__(self, canal_destino: discord.TextChannel, cargo_mencao: discord.Role | None, identidade: dict, cor_padrao: str):
        super().__init__()
        self.canal_destino = canal_destino
        self.cargo_mencao = cargo_mencao
        self.identidade = identidade
        self.cor_padrao = cor_padrao

    async def on_submit(self, interaction: discord.Interaction):
        try:
            embed = embed_base(
                titulo=self.titulo_anuncio.value,
                descricao=self.descricao_anuncio.value,
                cor_hex=self.cor_padrao,
                identidade=self.identidade,
            )

            if self.imagem_url.value:
                embed.set_image(url=self.imagem_url.value)

            conteudo = self.cargo_mencao.mention if self.cargo_mencao else None

            await self.canal_destino.send(content=conteudo, embed=embed)
            await interaction.response.send_message(
                embed=embed_sucesso("Anúncio publicado", f"Anúncio enviado em {self.canal_destino.mention}."), ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_erro("Sem permissão", "Não tenho permissão para enviar mensagens nesse canal."), ephemeral=True
            )
        except discord.HTTPException:
            logger.exception("Erro ao enviar anúncio")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível enviar o anúncio."), ephemeral=True)


class AnunciosCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="anunciar", description="Cria e envia um anúncio com embed personalizada")
    @app_commands.default_permissions(administrator=True)
    @apenas_administrador()
    @app_commands.describe(canal="Canal onde o anúncio será enviado", mencionar_cargo="Cargo a ser mencionado junto ao anúncio (opcional)")
    async def cmd_anunciar(self, interaction: discord.Interaction, canal: discord.TextChannel, mencionar_cargo: discord.Role = None):
        try:
            config = await gerenciador_dados.obter_config_guild(interaction.guild_id)
            config_anuncios = config["anuncios"]
            identidade = {
                "logo_url": config_anuncios.get("logo_url", ""),
                "rodape": config_anuncios.get("rodape", "CineTrigger"),
                "cor_padrao": config_anuncios.get("cor_padrao"),
            }
            modal = ModalAnuncio(canal, mencionar_cargo, identidade, config_anuncios.get("cor_padrao"))
            await interaction.response.send_modal(modal)
        except Exception:
            logger.exception("Erro ao abrir modal de anúncio")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível abrir o formulário de anúncio."), ephemeral=True)

    grupo_anuncios = app_commands.Group(
        name="anuncios", description="Configuração da aparência dos anúncios", default_permissions=discord.Permissions(administrator=True)
    )

    @grupo_anuncios.command(name="aparencia", description="Personaliza cor, logo e rodapé padrão dos anúncios")
    @apenas_administrador()
    async def cmd_aparencia(
        self,
        interaction: discord.Interaction,
        cor: str = None,
        logo_url: str = None,
        rodape: str = None,
    ):
        try:
            alteracoes = []

            if cor is not None:
                cor_normalizada = cor if cor.startswith("#") else f"#{cor}"
                try:
                    int(cor_normalizada.lstrip("#"), 16)
                except ValueError:
                    await interaction.response.send_message(
                        embed=embed_erro("Cor inválida", "Informe uma cor hexadecimal válida, ex: `#E63946`."), ephemeral=True
                    )
                    return
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["anuncios", "cor_padrao"], cor_normalizada)
                alteracoes.append(f"Cor: {cor_normalizada}")

            if logo_url is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["anuncios", "logo_url"], logo_url)
                alteracoes.append("Logo atualizada")

            if rodape is not None:
                await gerenciador_dados.atualizar_config_guild(interaction.guild_id, ["anuncios", "rodape"], rodape)
                alteracoes.append(f"Rodapé: {rodape}")

            if not alteracoes:
                await interaction.response.send_message(
                    embed=embed_erro("Nada para atualizar", "Informe ao menos um parâmetro para alterar."), ephemeral=True
                )
                return

            await interaction.response.send_message(embed=embed_sucesso("Aparência atualizada", "\n".join(alteracoes)), ephemeral=True)
        except Exception:
            logger.exception("Erro ao atualizar aparência de anúncios")
            await interaction.response.send_message(embed=embed_erro("Erro", "Não foi possível salvar a configuração."), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, SemPermissaoError):
            embed = embed_sem_permissao(str(error))
        else:
            logger.exception("Erro não tratado em comando de anúncios", exc_info=error)
            embed = embed_erro("Erro", "Ocorreu um erro inesperado ao executar este comando.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AnunciosCog(bot))


# ══════════════════════════════════════════════════════════════════
# SEÇÃO 15 — INICIALIZAÇÃO DO BOT
# ══════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    logger.info("Bot conectado como %s (ID: %s)", bot.user, bot.user.id)
    try:
        comandos_sincronizados = await bot.tree.sync()
        logger.info("Comandos sincronizados: %d", len(comandos_sincronizados))
    except discord.HTTPException:
        logger.exception("Erro ao sincronizar comandos com o Discord")
    logger.info("CineTrigger Bot está online e pronto.")


@bot.event
async def on_error(nome_evento, *args, **kwargs):
    logger.exception("Erro não tratado no evento: %s", nome_evento)


async def carregar_cogs():
    cogs_para_adicionar = [
        FilmeCog(bot),
        TicketsCog(bot),
        ModeracaoCog(bot),
        AutoRoleCog(bot),
        BoasVindasCog(bot),
        AnunciosCog(bot),
    ]
    for cog in cogs_para_adicionar:
        try:
            await bot.add_cog(cog)
            logger.info("Cog carregado: %s", type(cog).__name__)
        except Exception:
            logger.exception("Falha ao carregar o cog: %s", type(cog).__name__)
            raise


async def main():
    faltando = validar_variaveis_ambiente()
    if faltando:
        logger.error(
            "As seguintes variaveis de ambiente estao faltando: %s",
            ", ".join(faltando),
        )
        logger.error("Configure essas variaveis no painel do Render (Environment) ou no seu .env local.")
        sys.exit(1)

    # Inicia o servidor HTTP (health check do Render + callback OAuth do Google)
    # em uma thread separada, para nao bloquear o loop assincrono do bot.
    thread_http = threading.Thread(target=_iniciar_servidor_http, daemon=True)
    thread_http.start()

    async with bot:
        await carregar_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot encerrado manualmente.")
