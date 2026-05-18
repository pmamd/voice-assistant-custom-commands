# Contributing to Voice Assistant with Custom Commands

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and constructive in all interactions
- Follow the existing code style and conventions
- Test your changes before submitting

## Development Workflow

### 1. Fork and Clone

```bash
git clone --recursive git@github.com:pmamd/voice-assistant-custom-commands.git
cd voice-assistant-custom-commands
```

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `test/` - Test improvements
- `refactor/` - Code refactoring

### 3. Make Your Changes

**Before writing code:**
- Read the relevant documentation in `docs/`
- Check existing issues and PRs to avoid duplication
- For large changes, open an issue first to discuss

**Code requirements:**
- Follow existing code style
- Add comments for complex logic
- Update documentation if behavior changes
- Add tests for new functionality

**Build and test:**
```bash
# Build
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j

# Run tests
bash tests/test_e2e_startup.sh
python3 -m unittest tests.test_real_interrupt -v
```

### 4. Commit Your Changes

Follow conventional commit format:
```
type(scope): brief description

Longer description if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

Example:
```
feat(tools): add weather forecast tool

Adds weather_forecast tool with OpenWeatherMap API integration.
Includes unit tests and documentation updates.

Fixes #45
```

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

**Pull Request Checklist:**
- [ ] Code builds successfully
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No debugging code left in (console.log, print statements)
- [ ] No large files added (models, binaries)
- [ ] CHANGELOG.md updated (if applicable)

## What We're Looking For

**High-priority contributions:**
- Bug fixes with test cases
- Documentation improvements
- New tool implementations (see `docs/TOOL_SYSTEM.md`)
- Performance optimizations
- Test coverage improvements

**Please avoid:**
- Formatting-only changes without functional improvements
- Large refactors without prior discussion
- Adding dependencies without justification
- Breaking changes without migration path

## Testing Requirements

All contributions must include tests:

**For new features:**
- Unit tests for new functions
- Integration tests if it affects the pipeline
- Update test documentation

**For bug fixes:**
- Regression test that fails before fix
- Verify test passes after fix

**Run the full test suite:**
```bash
# Quick smoke tests
bash tests/test_e2e_startup.sh

# Full test suite (requires Wyoming-Piper running)
python3 -m unittest tests.test_real_interrupt.TestWyomingStopMechanics -v
python3 -m unittest tests.test_wyoming_piper_unit.TestLLMOutputQuality -v
```

## Code Review Process

1. Maintainer reviews PR within 3-5 business days
2. Address feedback and update PR
3. Once approved, maintainer merges to master
4. Your contribution is live!

## Questions?

- Open an issue for questions about contributing
- Check existing documentation in `docs/`
- Review closed PRs for examples

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

---

Thank you for contributing! 🎉
