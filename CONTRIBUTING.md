# Contributing to Ekora

Thank you for your interest in contributing to Ekora! Please read the guidelines below to help keep the codebase clean, robust, and maintainable.

---

## 1. Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/Ekora.git
   cd Ekora
   ```
2. **Set up virtual environment**:
   - Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - macOS / Linux:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 2. Branch Naming Conventions

- **Feature branches**: `feature/your-feature-name`
- **Bug fixes**: `bugfix/issue-description`
- **Refactoring & Performance**: `polish/description`
- **Documentation**: `docs/topic-name`

---

## 3. Code Standards & Style Guide

- **Coding Conventions**: Follow Python PEP-8 coding style.
- **Color Palettes**: All color representations must be BGR tuples matching OpenCV formats.
- **Type Annotations**: Add parameter and return type annotations to all public functions and class methods.
- **Docstrings**: Document classes and methods using standard NumPy or Google format. Focus docstrings on "why" a method exists rather than "what" it does.
- **No Absolute Paths**: All file paths must be relative (utilizing `pathlib.Path` or `__file__` directories) to allow portability.

---

## 4. Pull Request & Commit Guidelines

- **Atomic Commits**: Keep commits small and focused on single changes.
- **Commit Messages**: Start with a structured prefix:
  - `feat:` for new capabilities
  - `fix:` for bug fixes
  - `docs:` for documentation updates
  - `perf:` for latency/memory optimizations
- **Test validation**: Run all programmatic verification tests before pushing your branch:
  ```bash
  python -m pytest tests/
  ```
