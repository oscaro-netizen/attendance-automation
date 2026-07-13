# Developer Guide

This guide provides information for developers working on the Slack to MarsOS Attendance Automation Platform.

## Getting Started

Refer to the main `README.md` for instructions on setting up your local development environment using Docker Compose.

## Project Structure

Familiarize yourself with the project structure outlined in `README.md` to understand where different components reside.

## Database Management

### Models

SQLAlchemy models are defined in `app/models/models.py`. These define the structure of the database tables and their relationships.

### Migrations (Alembic)

Database schema changes are managed using Alembic. 

-   **Generate a new migration**: 
    ```bash
    docker compose run --rm app alembic revision --autogenerate -m "<description_of_changes>"
    ```
-   **Apply migrations**: 
    ```bash
    docker compose run --rm app alembic upgrade head
    ```
-   **Revert migrations**: 
    ```bash
    docker compose run --rm app alembic downgrade -1
    ```

## API Endpoints

The FastAPI application exposes several API endpoints. Refer to the automatically generated Swagger UI at `http://localhost:8000/docs` for detailed documentation of all available endpoints, their request/response schemas, and example usage.

Key API modules:
-   `app/api/health.py`: Health check endpoint.
-   `app/api/slack_events.py`: Endpoint for receiving Slack Events API requests.
-   `app/api/employees.py`: Endpoints for managing employee records.
-   `app/api/attendance.py`: Endpoints for managing attendance logs and retries.

## Slack Integration

-   **Event Handling**: Slack events are received and processed by the `app/api/slack_events.py` endpoint. 
-   **Signature Verification**: All incoming Slack requests are verified using the `app/middleware/slack_verification.py` middleware to ensure authenticity.
-   **Message Validation**: The `app/slack/validator.py` module contains logic for validating the format of incoming Slack messages to identify valid 
attendance start reports.

## MarsOS Integration

The `app/marsos/provider.py` defines the `AttendanceProvider` interface and its implementations (`MarsOSAPIProvider` and `MarsOSPlaywrightProvider`). The `app/marsos/factory.py` provides a way to switch between these implementations based on configuration.

-   **Playwright**: If MarsOS does not provide a suitable API, Playwright is used for browser automation to interact with the MarsOS web interface. Playwright logic is encapsulated in `app/marsos/provider.py`.

## Background Tasks (Celery)

Long-running tasks, such as interacting with MarsOS, are offloaded to Celery workers to prevent blocking the main FastAPI application. The Celery worker is defined in `app/workers/celery_worker.py`.

## Logging

Loguru is used for structured logging throughout the application. All significant operations and errors are logged to provide visibility and aid in debugging. The `AuditLogMiddleware` in `app/middleware/security.py` provides basic request logging.

## Security

Security considerations are paramount. Key aspects include:
-   **Slack Signature Verification**: Ensures that incoming Slack requests are legitimate.
-   **Secret Management**: Environment variables are used for sensitive information, with a recommendation for a secrets manager in production.
-   **Input Validation**: Pydantic schemas are used to validate incoming API request data.
-   **Error Handling**: Robust error handling is implemented to prevent sensitive information leakage.

## Testing

Tests are located in the `tests/` directory and cover:
-   **Unit Tests**: For individual functions and classes.
-   **Integration Tests**: For interactions between different components (e.g., API endpoints and database).
-   **End-to-End Tests**: (To be expanded) For simulating full user flows.

Run tests using `pytest`:
```bash
docker compose exec app pytest
```

## Code Quality

-   **Linting and Formatting**: Ruff and Black are used to maintain consistent code style.
-   **Type Checking**: Mypy is used for static type checking to catch potential errors early.
-   **Docstrings and Type Hints**: All modules, classes, and functions should have clear docstrings and type hints.
-   **Dependency Injection**: FastAPI's dependency injection system is utilized for managing dependencies.
-   **Repository Pattern**: Database interactions are abstracted using the repository pattern.
-   **SOLID Principles & Clean Architecture**: The project aims to adhere to these principles for maintainability and scalability.
