# Security Policy

## Scope

AI Recovery Engine is an **educational simulation** — not a production payment system. It uses synthetic, seeded data and makes no network calls except when you explicitly opt into the optional Claude brain (`--brain claude`).

## Reporting a vulnerability

If you believe you have found a security issue in this repository (for example, accidental secret exposure, unsafe defaults in optional LLM integration, or CI misconfiguration), please report it responsibly:

1. **Do not** open a public issue for sensitive findings
2. Email the repository owner via their GitHub profile contact, or open a private security advisory on GitHub if enabled
3. Include steps to reproduce and the files affected

## What is in scope

- Committed secrets or credentials
- Unsafe handling of `ANTHROPIC_API_KEY` in optional LLM mode
- GitHub Actions workflow issues that could affect contributors

## What is out of scope

- Findings in synthetic demo data or simulated fraud spikes (these are intentional)
- Attacks against Groupon or any real payment infrastructure — this project is **not affiliated with Groupon** and does not connect to live systems
- General hardening of a production deployment pattern this repo does not implement

## Optional LLM usage

The default path uses a deterministic heuristic brain with zero external calls. If you use `ClaudeBrain`:

- Provide `ANTHROPIC_API_KEY` via environment variable only — never commit it
- The brain's output is validated against the same bounded action space and verifier as the heuristic; errors fall back safely

We aim to respond to valid reports within a reasonable timeframe and will credit reporters when fixes are published, if they wish.
