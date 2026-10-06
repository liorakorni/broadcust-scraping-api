import os

# Loaded from Lambda environment (serverless.yml -> SSM /broadcust/scraping-api/*) or local shell.
perplexity_api_key = os.environ.get("PERPLEXITY_API_KEY", "")
api_secret_key = os.environ.get("API_SECRET_KEY", "")
firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY", "")
serpapi_key = os.environ.get("SERPAPI_KEY", "")
