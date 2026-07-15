# Contributing to Attendance Automation Platform

We welcome contributions to the Attendance Automation Platform! By contributing, you help us improve the reliability, security, and functionality of the system.

Please take a moment to review this document to understand our contribution guidelines.

## How to Contribute

1.  **Fork the Repository**: Start by forking the project repository to your GitHub account.
2.  **Clone Your Fork**: Clone your forked repository to your local machine:
    ```bash
    git clone https://github.com/your-username/attendance-automation.git
    cd attendance-automation
    ```
3.  **Create a New Branch**: Create a new branch for your feature or bug fix. Use a descriptive name (e.g., `feature/add-new-report`, `bugfix/playwright-login-issue`).
    ```bash
    git checkout -b feature/your-feature-name
    ```
4.  **Set up Development Environment**: Follow the instructions in `README.md` to set up your local development environment using Docker Compose.
5.  **Make Your Changes**: Implement your feature or fix the bug. Ensure your code adheres to the project's coding standards (see Code Style).
6.  **Write Tests**: Add unit and/or integration tests for your changes. Ensure existing tests pass and new tests cover your modifications adequately.
7.  **Run Tests**: Before committing, run the entire test suite:
    ```bash
    docker compose exec app pytest
    ```
8.  **Update Documentation**: If your changes affect the functionality, configuration, or deployment, update the relevant documentation files (`README.md`, `docs/deployment.md`, `docs/developer_guide.md`).
9.  **Commit Your Changes**: Write clear and concise commit messages. Follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.
    ```bash
    git commit -m "feat: Add new feature for X"
    ```
10. **Push to Your Fork**: Push your branch to your forked repository:
    ```bash
    git push origin feature/your-feature-name
    ```
11. **Create a Pull Request**: Open a pull request from your branch to the `main` branch of the original repository. Provide a detailed description of your changes and reference any related issues.

## Code Style

We use `ruff` for linting and `black` for code formatting. Please ensure your code is formatted correctly before submitting a pull request.

```bash
# Install dev dependencies (if not already installed)
poetry install --with dev

# Run ruff linter
poetry run ruff check .

# Run black formatter
poetry run black .
```

## Testing Guidelines

*   **Unit Tests**: Cover individual functions and methods in isolation.
*   **Integration Tests**: Verify the interaction between different components (e.g., API endpoints with services, services with repositories).
*   **Playwright Tests**: Ensure the MarsOS automation flows are robust and handle various scenarios.

Aim for high test coverage, especially for critical business logic and external integrations.

## Security Best Practices

*   Never hardcode sensitive information.
*   Always validate user input.
*   Be mindful of potential replay attacks and implement idempotency where necessary.
*   Ensure proper error handling and logging without exposing sensitive details.

## Issue Reporting

If you find a bug or have a feature request, please open an issue on the GitHub issue tracker. Provide as much detail as possible, including steps to reproduce the bug, expected behavior, and your environment setup.

Thank you for contributing!
