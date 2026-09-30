from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/eve_diagnostics"
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ADMIN_EMAIL: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
