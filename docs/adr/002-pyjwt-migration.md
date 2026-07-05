# ADR-002: PyJWT Migration

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** AI for Investor Team

## Context

The project was using `python-jose` for JWT encoding and decoding. This library has been
unmaintained since 2022 with no new releases, open security issues, and no response to
pull requests. Relying on an unmaintained cryptographic library poses a security risk,
especially for authentication tokens that protect user accounts and trading data.

Additionally, `python-jose` pulls in multiple backend dependencies (e.g., `ecdsa`,
`pyasn1`) that increase the attack surface.

## Decision

Migrate from `python-jose` to `PyJWT` (the `pyjwt` package), which is:

- Actively maintained with regular releases
- Widely adopted (used by Django REST Framework, Flask-JWT-Extended, etc.)
- Minimal dependency footprint (only `cryptography` as optional backend)
- Well-documented with clear migration paths

API changes required:

```python
# Before (python-jose)
from jose import jwt, JWTError
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

# After (PyJWT)
import jwt
from jwt.exceptions import InvalidTokenError
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
```

Key differences:
- Exception class renamed: `JWTError` → `InvalidTokenError`
- `jwt.encode()` returns `str` directly (not `bytes` in newer versions)
- Import path changes from `jose` to `jwt`

## Consequences

### Positive

- Active maintenance ensures timely security patches
- Smaller dependency tree reduces supply-chain risk
- Better documentation and community support
- Compatible with Python 3.10+ type hints

### Negative

- Slightly different API surface requires updating all JWT-related code
- Exception handling must be updated across auth middleware and services
- Team members familiar with python-jose API need to adjust

### Neutral

- Both libraries support the same JWT algorithms (HS256, RS256, ES256)
- Token format is identical — no migration needed for existing tokens
- Performance characteristics are comparable for our use case
