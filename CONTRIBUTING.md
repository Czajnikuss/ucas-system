# Contributing to UCAS

Thank you for your interest in contributing to UCAS. We welcome issues, bug reports, and pull requests. To make contributions smooth, please follow these guidelines.

## How to contribute

1. Check existing issues and PRs to avoid duplicates.
2. Open an issue for significant changes or design discussions before implementing large features.
3. Fork the repository and create a descriptive branch name (e.g. `feature/add-llm-timeout`, `fix/docker-compose-health`).
4. Write tests for new features or bug fixes when applicable.
5. Keep commits small and focused. Rebase/squash before opening a PR if appropriate.
6. Ensure linters and basic tests pass locally.

## Pull request checklist

- Provide a clear description of the change and motivation.
- Include related issue number, if any.
- Add tests for bug fixes or features.
- Update `README.md` or docs if public behavior changes.

## Code style and tests

- Python services use standard formatting (black / flake8 recommended). If you add a new service, include a `requirements.txt` and basic `Dockerfile`.
- Tests should be runnable via `pytest` inside the respective service container, e.g.:

```powershell
docker compose exec orchestrator pytest tests/
```

## CI and checks

If CI is configured, PRs should pass automated checks. If you need help configuring CI for a new service, open an issue.

## Local development tips

- Use `docker compose up` to start all services locally.
- Persisted models are stored in `volumes/models/` — do not commit large model files into the repo.

## Communication

Open issues for bugs or feature requests. For quick questions, reference an issue or open a draft PR.

---

Krótka uwaga po polsku:

Dziękujemy za zainteresowanie projektem. Jeśli chcesz wprowadzić większe zmiany, najlepiej najpierw otworzyć issue opisujące propozycję.
