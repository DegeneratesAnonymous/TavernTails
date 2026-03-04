# Login

> Screenshot auto-updated on every merge to `main` via the
> [screenshot-update](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/screenshot-update.yml) workflow.

![Login](https://raw.githubusercontent.com/DegeneratesAnonymous/TavernTails/main/docs/screenshots/02-login.png)

The sign-in form — accessible from the **Sign In** button on the landing page
or any unauthenticated quick-action tile.

## Fields

| Field | Description |
|---|---|
| **Email** | Registered account email address |
| **Password** | Account password (masked) |

## Actions

- **Sign In** — submits the credentials; on success a JWT access token is stored
  in `localStorage` and the user is redirected to the Dashboard.
- **Create account** — switches to the Sign-Up form without a page navigation.

## Dev Shortcut

In local development a **"Use dev login"** button auto-fills
`test@example.com / secret` so developers can reach the Dashboard in one click.
The button is hidden in production builds.

## Error Handling

Invalid credentials display a red inline error banner above the form.
Network errors (backend unreachable) surface a user-friendly message rather than
a raw HTTP status code.

## Email Verification

If an account exists but the email has not been verified, the login response
includes a verification prompt.  A token input field appears inline so the user
can paste the emailed code without leaving the page.

---

_← Back to [[Home]]_
