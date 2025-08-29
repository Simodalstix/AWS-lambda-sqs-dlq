# Contributing to AWS Lambda SQS DLQ

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Development Setup

1. **Prerequisites**
   - Python 3.11+
   - Node.js 20+
   - AWS CLI configured
   - Poetry (recommended)

2. **Setup**
   ```bash
   git clone https://github.com/username/AWS-lambda-sqs-dlq.git
   cd AWS-lambda-sqs-dlq
   poetry install
   ```

3. **Validate Setup**
   ```bash
   poetry run pytest
   cd infra && poetry run cdk synth
   ```

## Development Workflow

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Test your changes**
   ```bash
   poetry run pytest
   poetry run flake8 infra
   poetry run mypy infra --ignore-missing-imports
   cd infra && poetry run cdk synth
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   git push origin feature/your-feature-name
   ```

5. **Create Pull Request**
   - Provide clear description of changes
   - Reference any related issues
   - Ensure CI passes

## Code Standards

- **Python**: Follow PEP 8, use Black formatter
- **CDK**: Use TypeScript-style naming for constructs
- **Tests**: Write tests for new constructs and logic
- **Documentation**: Update README for user-facing changes

## Commit Messages

Use conventional commits format:
- `feat:` new features
- `fix:` bug fixes
- `docs:` documentation changes
- `test:` test additions/changes
- `refactor:` code refactoring

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas
- Check existing issues before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the MIT License.