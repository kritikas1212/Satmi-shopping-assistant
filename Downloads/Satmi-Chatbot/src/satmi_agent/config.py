from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    api_port: int = 8000
    llm_provider: str = "gemini"
    model_name: str = "gemini-2.0-flash"
    gemini_api_key: str | None = None
    llm_response_refinement_enabled: bool = False
    database_url: str = "sqlite:///./satmi_agent.db"
    shopify_store_domain: str | None = None
    shopify_admin_api_token: str | None = None
    shopify_api_version: str = "2025-01"
    auth_required: bool = False
    api_key: str | None = None
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    shopify_timeout_seconds: float = 15.0
    shopify_max_retries: int = 2
    observability_enabled: bool = True
    metrics_endpoint_enabled: bool = True
    metrics_endpoint_path: str = "/metrics"
    tracing_enabled: bool = False
    tracing_service_name: str = "satmi-chatbot"
    tracing_exporter: str = "otlp"
    tracing_otlp_endpoint: str = "http://localhost:4318/v1/traces"
    tracing_timeout_seconds: float = 5.0
    policy_kb_path: str = "./data/policy_kb.json"
    policy_retrieval_max_items: int = 3
    hitl_interrupt_enabled: bool = False
    async_cancel_enabled: bool = False
    redis_url: str | None = None
    cancel_queue_key: str = "satmi:cancel:queue"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
