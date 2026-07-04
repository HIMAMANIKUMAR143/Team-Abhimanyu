"""
Central configuration. Everything environment-specific lives here so the
rest of the app never reads os.environ directly.

For your team: if you add a new setting (e.g. a new API key), add it here
with a sensible default, then reference `settings.YOUR_SETTING` elsewhere.
Never hardcode secrets or URLs in other files.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/pollution_tracker"
    )

    # --- Gemini (image classification) ---
    # Leave blank to run in MOCK mode. When your key is ready, put it in
    # .env as GEMINI_API_KEY=... and restart the app. No code changes needed.
    GEMINI_API_KEY: str = "AIzaSyDOkWQJ0Gfx2qVYqJjbjv_C8hkdO8_weVY"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # --- App behavior ---
    # Radius (meters) within which two reports are considered the same
    # incident for duplicate/cluster detection.
    CLUSTER_RADIUS_METERS: float = 150.0
    # Time window (hours) within which two nearby reports are clustered.
    CLUSTER_TIME_WINDOW_HOURS: float = 72.0

    # Severity scoring weights — kept to 4 variables on purpose so it's
    # explainable in one breath during judge Q&A.
    SEVERITY_BASE_WEIGHTS: dict = {
        "garbage": 30,
        "water_pollution": 50,
        "air_pollution": 60,
        "industrial_waste": 70,
        "sewage": 55,
        "other": 25,
    }
    SEVERITY_DUPLICATE_BONUS: int = 10       # if 3+ reports in same cluster
    SEVERITY_DUPLICATE_THRESHOLD: int = 3
    SEVERITY_SENSITIVE_ZONE_BONUS: int = 15  # if near school/hospital (future use)

    @property
    def GEMINI_MOCK_MODE(self) -> bool:
        return not bool(self.GEMINI_API_KEY.strip())


settings = Settings()
