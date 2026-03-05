# Sign Up

> Screenshot auto-updated on every merge to `main` via the
> [screenshot-update](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/screenshot-update.yml) workflow.

![Sign Up](https://raw.githubusercontent.com/DegeneratesAnonymous/TavernTails/main/docs/screenshots/03-signup.png)

The account registration form — accessible from **Create Account** on the
landing page or the toggle link on the Login form.

## Fields

| Field | Notes |
|---|---|
| **Username** | Optional unique handle; used in multiplayer sessions |
| **Email** | Must be a valid address; used for login and notifications |
| **Password** | Minimum 8 characters recommended |

## Registration Flow

1. Submit the form — the backend creates a new `player` account and sends a
   verification email.
2. A verification code prompt appears inline (no page redirect).
3. Paste the six-digit code; on success the account is marked verified and a JWT
   is issued.
4. The user is immediately redirected to the Dashboard.

**Dev mode:** both email verification and the credential step are bypassed
automatically when `TAVERNTAILS_SEED_DEV_USER=1` is set on the backend.

## Validation

Client-side validation checks for a valid email format before submission.
Duplicate-email errors are surfaced inline from the API response.

---

_← Back to [[Home]]_
