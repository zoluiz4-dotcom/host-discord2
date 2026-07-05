"""
Configurações centrais da aplicação.
Tudo o que é sensível ou específico do ambiente (chaves, caminhos, origens
permitidas) vem de variáveis de ambiente — lidas de um arquivo .env local
em desenvolvimento, ou definidas diretamente no painel do Render (ou de
qualquer outro provedor) em produção. Nunca ficam hardcoded no código.
"""
import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INSECURE_KEY = "changeme"


class Settings(BaseSettings):
    # env_file só é lido se o arquivo existir (não existirá no Render,
    # onde as variáveis vêm do painel de "Environment" do serviço).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PANEL_API_KEY: str = DEFAULT_INSECURE_KEY
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    BOTS_DIR: str = "./bots_data"
    DATABASE_URL: str = "sqlite:///./panel.db"
    PORT: int = 8000
    USE_DOCKER: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def bots_dir_path(self) -> Path:
        path = Path(self.BOTS_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_running_on_render(self) -> bool:
        # O Render define essa variável automaticamente em todo serviço.
        return bool(os.environ.get("RENDER"))


settings = Settings()

# Aviso alto e explícito em produção se a chave padrão não foi trocada.
# Isso não bloqueia o boot (para não quebrar o primeiro deploy antes de
# configurar as env vars), mas deixa o risco impossível de ignorar nos logs.
if settings.PANEL_API_KEY == DEFAULT_INSECURE_KEY:
    print(
        "\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        "AVISO DE SEGURANCA: PANEL_API_KEY nao foi configurada (usando valor\n"
        "padrao inseguro). Qualquer pessoa pode controlar seus bots e ler\n"
        "seus arquivos .env. Defina PANEL_API_KEY nas variaveis de ambiente\n"
        "do seu servico no Render (Settings > Environment) antes de usar\n"
        "o painel de verdade.\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n",
        file=sys.stderr,
    )
