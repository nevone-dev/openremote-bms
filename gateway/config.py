from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    or_base_url: str = "https://localhost"
    or_realm: str = "master"
    or_username: str = "admin"
    or_password: str = "secret"

    # MQTT — port 8883 is the TLS port exposed by the OR proxy
    mqtt_host: str = "localhost"
    mqtt_port: int = 8883
    mqtt_use_tls: bool = True
    mqtt_client_id: str = "gateway"
    # Override if OR MQTT expects a different format (e.g. "master:admin")
    mqtt_username: str = ""
    mqtt_password: str = ""

    # Refresh token this many seconds before it expires
    token_refresh_margin: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
