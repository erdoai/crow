from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CROW_")

    # Database — Railway Postgres (provisioned via scaffold)
    database_url: str = ""

    # Claude API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # External systems
    devbot_url: str = "http://localhost:8484"
    pilot_url: str = "http://localhost:9721"
    erdo_url: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8100

    # Worker auth
    worker_api_key: str = "changeme"

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
