"""应用配置。所有可变项来自环境变量 / backend/.env，代码中不出现密钥字面量。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "直播运营虚拟仿真实训平台"
    api_prefix: str = "/api/v1"
    secret_key: str = "dev-only-secret-change-in-env"
    token_expire_minutes: int = 720

    database_url: str = (
        "mysql+pymysql://root:CHANGE_ME@127.0.0.1:3306/live_training?charset=utf8mb4"
    )
    db_echo: bool = False

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: str = "var/uploads"

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 30.0

    asr_base_url: str = ""
    asr_api_key: str = ""
    asr_timeout_seconds: float = 15.0

    sim_tick_min_interval_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
