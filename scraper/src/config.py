"""Configuration management for the scraper"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for scraper settings"""

    # Database configuration
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "wandering_inn_tracker")
    DB_USER: str = os.getenv("DB_USER", "wandering_inn")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "dev_password_change_in_production")

    # Scraper configuration
    BASE_URL: str = os.getenv("BASE_URL", "https://wanderinginn.com")
    REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "10"))  # Respects robots.txt crawl-delay
    START_CHAPTER: int = int(os.getenv("START_CHAPTER", "1"))
    MAX_CHAPTERS: int = int(os.getenv("MAX_CHAPTERS", "0"))

    # User agent for requests
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    @classmethod
    def get_db_connection_string(cls) -> str:
        """Get PostgreSQL connection string"""
        return (
            f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}"
            f"@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        )

    @classmethod
    def get_db_params(cls) -> dict:
        """Get database connection parameters as dict"""
        return {
            "host": cls.DB_HOST,
            "port": cls.DB_PORT,
            "database": cls.DB_NAME,
            "user": cls.DB_USER,
            "password": cls.DB_PASSWORD,
        }
