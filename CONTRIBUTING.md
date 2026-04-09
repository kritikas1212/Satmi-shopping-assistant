# Contributing

## Safe GitHub Auth And Push Workflow

1. Use SSH remote for GitHub.

```bash
git remote set-url origin git@github.com:kritikas1212/Satmi-shopping-assistant.git
```

2. Validate GitHub SSH auth before pushing.

```bash
ssh -T git@github.com
```

Expected output includes: `Hi kritikas1212! You've successfully authenticated...`

3. Push the active branch (this repo uses `main`).

```bash
git push origin main
```

## Pre-commit Secret Scanner

Install and enable hooks once per machine:

```bash
python -m pip install pre-commit
pre-commit install
```

Run hooks manually on all files:

```bash
pre-commit run --all-files
```

The local secret scan blocks commits that include:
- credential files like `.env` or Firebase service account JSON files
- common secret signatures such as private keys, Gemini API keys, and Shopify admin tokens

## If A Push Is Blocked By GitHub Push Protection

1. Identify the blocked file from the GitHub error output.
2. Remove the secret from tracked history before pushing again.
3. Re-commit only safe files.

Common helper commands:

```bash
git restore --staged <file>
git rm --cached <file>
git commit --amend
git push origin main
```
