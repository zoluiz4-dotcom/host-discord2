"""
Configurações centrais da aplicação.
Tudo o que é sensível ou específico do ambiente (chaves, caminhos, origens
permitidas) vem do arquivo .env e nunca fica hardcoded no código.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PANEL_API_KEY: str = "changeme"
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


settings = Settings()
