class Settings:
    # Fixed values: the engine reads no environment variable and no settings
    # file.

    # Inference
    WORKER_PAGE_THRESHOLD: int = 10  # Min number of pages per worker in parallel


settings = Settings()
