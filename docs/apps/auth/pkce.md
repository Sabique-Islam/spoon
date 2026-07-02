# `pkce.py` — PKCE Code Verifier and Challenge Generation

`pkce.py` implements RFC 7636 Proof Key for Code Exchange (PKCE) for OAuth 2.0 public clients and enhanced confidential-client flows. It generates a random code verifier and the corresponding S256 code challenge used in authorization requests for Google Drive and Microsoft Outlook.

---

## Role in Spoon Architecture

PKCE protects the authorization code exchange: even if an attacker intercepts the authorization `code` from the redirect, they cannot exchange it without the original code verifier. Spoon stores the verifier server-side in `state.py` (via `generate_oauth_state(pkce_verifier=verifier)`) and sends only the challenge to the authorization server.

```
build_authorization_url()
        │
        ├── generate_pkce_pair()  ──▶ verifier, challenge
        │
        ├── state = generate_oauth_state(pkce_verifier=verifier)  [stored server-side]
        │
        └── URL params: code_challenge=challenge, code_challenge_method=S256

callback
        │
        └── exchange_code_for_token(code, pkce_verifier=state_entry.pkce_verifier)
                    │
                    └── POST includes code_verifier=verifier
```

Used by: `gdrive_oauth.py`, `outlook_oauth.py`. Not used by Notion or Slack in the current codebase.

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `base64` | stdlib | URL-safe Base64 encoding of SHA-256 digest |
| `hashlib` | stdlib | SHA-256 hashing for S256 challenge method |
| `secrets` | stdlib | Cryptographically secure random verifier |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/gdrive_oauth.py` | `generate_pkce_pair` |
| `app/auth/outlook_oauth.py` | `generate_pkce_pair` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1 | `import base64` | Encodes the SHA-256 hash as Base64 for the challenge. |
| 2 | `import hashlib` | Provides `sha256()` for the S256 challenge method. |
| 3 | `import secrets` | Generates the code verifier with `token_urlsafe`. |
| 4 | *(blank)* | Separator. |
| 6–11 | `generate_pkce_pair()` | Returns `(verifier, challenge)` tuple per RFC 7636. |
| 7 | `verifier = secrets.token_urlsafe(64)` | Random verifier, 64 bytes entropy → ~86 URL-safe chars (within 43–128 char RFC range). |
| 8–10 | Challenge computation | `SHA256(verifier)` → URL-safe Base64 → strip padding `=` |
| 8 | `hashlib.sha256(verifier.encode()).digest()` | S256 method: hash ASCII-encoded verifier. |
| 9–10 | `base64.urlsafe_b64encode(...).rstrip(b"=")` | URL-safe Base64 without padding, per PKCE spec. |
| 10 | `.decode()` | Convert bytes to str for URL query parameter. |
| 11 | `return verifier, challenge` | Caller stores verifier in state; puts challenge in auth URL. |

---

## Key Functions

| Function | Returns | Description |
|----------|---------|-------------|
| `generate_pkce_pair()` | `tuple[str, str]` | `(code_verifier, code_challenge)` using method S256. |

There are no classes or module-level constants.

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| S256 only (not plain) | Recommended method; resistant to verifier interception | Slightly more CPU than `plain` | Support `plain` for legacy servers |
| `token_urlsafe(64)` for verifier | High entropy; URL-safe charset | Longer verifier string | Fixed 43-char minimum length |
| Strip Base64 padding | Matches PKCE Base64url without padding convention | Must match on validation side (Google/Microsoft handle this) | Keep padding |
| Single function module | Minimal, easy to audit | No challenge method parameter | Class-based PKCE helper with configurable method |
| No persistence here | Verifier lifecycle owned by `state.py` | Two modules must be used together | Store verifier inside `pkce.py` |

---

## Security Considerations

- **Verifier entropy**: 64 bytes from `secrets` provides strong randomness suitable for PKCE.
- **Verifier never in browser URL**: Only stored server-side and sent during token exchange (POST body), reducing exposure compared to passing verifier in redirect URLs.
- **S256**: Prevents attackers who see the challenge from deriving the verifier (unlike `plain` method).
- **One-time pairing**: Each authorization attempt should call `generate_pkce_pair()` fresh; reusing verifiers defeats PKCE purpose.
- **Coupling with state**: If verifier is lost (e.g. server restart with in-memory state), token exchange fails — users must restart OAuth flow.

---

## When and How to Extend

### Add PKCE to a new provider

1. In `build_authorization_url()`:

```python
from app.auth.pkce import generate_pkce_pair
from app.auth.oauth import generate_oauth_state

verifier, challenge = generate_pkce_pair()
params["state"] = generate_oauth_state(pkce_verifier=verifier)
params["code_challenge"] = challenge
params["code_challenge_method"] = "S256"
```

2. In `exchange_code_for_token()`, accept `pkce_verifier` and add to token POST payload:

```python
if pkce_verifier:
    payload["code_verifier"] = pkce_verifier
```

3. Ensure `app/routes.py` callback passes `state_entry.pkce_verifier` (already implemented).

### Support plain method (not recommended)

Add optional parameter `method: Literal["S256", "plain"]` and branch challenge computation. Only use if a provider rejects S256.

### Unit testing

Verify challenge equals Base64url(SHA256(verifier)) without padding for known verifier inputs.
