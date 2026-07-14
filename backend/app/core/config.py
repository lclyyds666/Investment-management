"""应用全局配置，统一从 .env 读取。"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    PROJECT_NAME: str = "山东出版供应链管理公司业务平台"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # 数据库
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "sd_publish_scm"
    DB_CHARSET: str = "utf8mb4"

    # JWT
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Redis（用于图形验证码存储 + 登录防爆破计数）。
    # 未配置或连接失败时，自动回退到进程内存实现，功能不受影响（详见 core/store.py）。
    REDIS_URL: str = ""

    # 登录安全
    CAPTCHA_ENABLED: bool = True          # 是否强制图形验证码
    CAPTCHA_TTL_SECONDS: int = 120        # 验证码有效期
    LOGIN_MAX_FAILURES: int = 5           # 连续失败上限
    LOGIN_LOCK_MINUTES: int = 30          # 达上限后锁定时长
    DEFAULT_PASSWORD: str = "123456"      # 超管重置后的默认密码
    PASSWORD_MIN_LENGTH: int = 6          # 密码最小长度

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = []

    # AI 智能体（DeepSeek，OpenAI 兼容协议）
    # 未配置 DEEPSEEK_API_KEY 时，AI 诊断自动回退到内置规则引擎，不影响可用性。
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    AI_TIMEOUT_SECONDS: float = 40.0

    # 客户 AI 尽调：Web 搜索（默认博查 Bocha，国内可直连）。
    # 未配置 SEARCH_API_KEY 时自动跳过联网检索并在报告中标注（不影响其余段落）。
    SEARCH_PROVIDER: str = "bocha"
    SEARCH_API_KEY: str = ""
    SEARCH_BASE_URL: str = "https://api.bochaai.com/v1/web-search"
    SEARCH_COUNT: int = 8
    # 上传的准入资料原始文件存放目录（相对后端工作目录；已 gitignore）。
    UPLOAD_DIR: str = "uploads"

    @property
    def AI_ENABLED(self) -> bool:
        """是否具备调用真实大模型的条件。"""
        return bool(self.DEEPSEEK_API_KEY.strip())

    @property
    def SEARCH_ENABLED(self) -> bool:
        """是否具备联网检索条件（配了搜索 API Key）。"""
        return bool(self.SEARCH_API_KEY.strip())

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset={self.DB_CHARSET}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
