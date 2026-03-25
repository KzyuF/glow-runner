from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    admin_telegram_id: int
    marzban_address: str
    marzban_username: str
    marzban_password: str
    database_url: str = "sqlite+aiosqlite:///data/bot.db"

    class Config:
        env_file = "config/.env"


settings = Settings()
