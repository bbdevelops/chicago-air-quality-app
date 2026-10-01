# Deployment Guide

## 1. Prerequisites
- Python 3.13
- The committed `data/clean/` files must be present (or generated via `python run_pipeline.py`).

## 2. Local Environment
Install dependencies and run the dashboard locally:
```bash
pip install -r requirements.txt
python -m streamlit run streamlit_app/app.py
```

## 3. Docker
Build and run the application as a non-root user via Docker. The included `.dockerignore` prevents raw data and secrets from being copied into the image.
```bash
docker build -t chicago-air-quality .
docker run --rm -p 8501:8501 chicago-air-quality
```

## 4. Data Freshness (GitHub Actions)
A GitHub Actions workflow (`.github/workflows/update_data.yml`) is configured to run daily.
- It pulls the latest Socrata data and commits changes to `data/clean/`.
- **Manual Trigger:** You can trigger it manually from the "Actions" tab in GitHub.
- **Secrets Required:** You must configure `SOCRATA_APP_TOKEN` and `SOCRATA_APP_SECRET` as repository secrets.

## 5. Secrets
- **Local:** Set `SOCRATA_APP_TOKEN` and `SOCRATA_APP_SECRET` in your `.env` file. (Optional: `EPA_API_EMAIL` and `EPA_API_KEY` for regulatory reference data).
- **GitHub Actions:** Add these same keys as Repository Secrets under Settings > Secrets and variables > Actions.

## 6. Health Check
The Dockerfile configures a health check that polls Streamlit's internal health endpoint:
```bash
curl --fail http://localhost:8501/_stcore/health
```

## 7. Reverse Proxy
For production hosting, place a reverse proxy (like Nginx, Caddy, or Traefik) in front of port 8501 to handle HTTPS and domain routing.
