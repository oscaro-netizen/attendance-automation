# Deployment Guide

This document outlines the steps to deploy the Slack to MarsOS Attendance Automation Platform to a production environment.

## Prerequisites

- Docker and Docker Compose installed on your deployment server.
- A PostgreSQL database instance (can be self-hosted or a managed service).
- A Redis instance for Celery broker and caching.
- Slack App configured with Events API and necessary permissions.
- MarsOS credentials (API key or login credentials for Playwright).
- Environment variables configured for your production environment.

## Environment Variables - **Crucial for Production Deployment**

Ensure the following environment variables are set in your production environment. It is highly recommended to use a secrets management service (e.g., AWS Secrets Manager, HashiCorp Vault) rather than `.env` files in production. **All placeholder values must be replaced with your actual production credentials.**

| Variable              | Description                                                                 | Placeholder to Replace                               |
| :-------------------- | :-------------------------------------------------------------------------- | :--------------------------------------------------- |
| `SLACK_SIGNING_SECRET`| Your Slack App's Signing Secret for request verification.                   | `your_slack_signing_secret`                          |
| `SLACK_BOT_TOKEN`     | Your Slack Bot User OAuth Token (starts with `xoxb-`).                     | `xoxb-your_slack_bot_token`                          |
| `SLACK_CHANNEL_ID`    | (Optional) The specific Slack channel ID to listen to for attendance reports. If not set, the bot will listen to all public channels it's invited to. |
| `DATABASE_URL`        | Connection string for your PostgreSQL database (e.g., `postgresql+asyncpg://user:password@host:port/dbname`). **Ensure this points to your production database.** | `postgresql+asyncpg://user:password@db:5432/attendance_db` |
| `REDIS_URL`           | Connection string for your Redis instance (e.g., `redis://host:port/db`).   | `redis://redis:6379/0`                               |
| `MARSOS_BASE_URL`     | The base URL of your MarsOS instance (e.g., `https://marsos.yourcompany.com`). **This is the URL Playwright will navigate to.** | `https://marsos.example.com`                         |
| `MARSOS_API_KEY`      | (Optional) API key for MarsOS if using `MarsOSAPIProvider`.                 |
| `PLAYWRIGHT_HEADLESS` | Set to `true` for headless browser operation in Playwright (recommended for production). |

## Deployment Steps

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-repo/attendance-automation.git
    cd attendance-automation
    ```

2.  **Build Docker Images**:
    ```bash
    docker compose build
    ```

3.  **Run Database Migrations**:
    Before starting the application, apply any pending database migrations.
    ```bash
    docker compose run --rm app alembic upgrade head
    ```

4.  **Start Services**:
    Start the application, worker, database, and Redis services.
    ```bash
    docker compose up -d
    ```
    The `-d` flag runs the containers in detached mode.

5.  **Configure Nginx/Load Balancer**:
    If deploying behind a reverse proxy or load balancer (highly recommended for production), configure it to forward traffic to the FastAPI application (default port 8000).

6.  **Monitor Logs**:
    Monitor the application logs to ensure everything is running as expected.
    ```bash
    docker compose logs -f
    ```

## CI/CD Configuration (Example with GitHub Actions)

Below is a basic example of a GitHub Actions workflow for building and deploying the application. This assumes you have configured your repository secrets for `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `MARSOS_BASE_URL`, etc.

```yaml
name: Deploy to Production

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and push Docker images
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: your-docker-username/attendance-automation:latest

      - name: Deploy to Server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USERNAME }}
          key: ${{ secrets.SSH_KEY }}
          script:
            cd /path/to/your/app
            docker compose pull
            docker compose up -d --remove-orphans
            docker compose run --rm app alembic upgrade head
            docker image prune -f
```

## Troubleshooting

-   **Container not starting**: Check `docker compose logs <service_name>` for specific error messages.
-   **Database connection issues**: Verify `DATABASE_URL` and ensure the database service is reachable from the application container.
-   **Slack signature verification failed**: Double-check `SLACK_SIGNING_SECRET` and ensure your server's time is synchronized.
-   **Playwright issues**: Ensure all Playwright dependencies are correctly installed in the Docker image. Check screenshots saved on failure for visual debugging.
