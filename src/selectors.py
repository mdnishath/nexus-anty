"""
src/selectors.py — Centralized CSS/text selector constants.

All shared selectors for Google login UI are defined here.
When Google updates its UI, update in ONE place — not in login_brain.py,
screen_detector.py, and login_flow.py independently.

Usage:
    from src.selectors import EMAIL_SELECTORS, PASSWORD_SELECTORS, NEXT_BUTTON_SELECTORS
"""

# ── Email / username input ────────────────────────────────────────────────────
EMAIL_SELECTORS: list[str] = [
    'input[type="email"]',
    'input[name="identifier"]',
    'input[autocomplete="username"]',
    '#identifierId',
    'input[id="identifierId"]',
]

# ── Password input ────────────────────────────────────────────────────────────
PASSWORD_SELECTORS: list[str] = [
    'input[type="password"]',
    'input[name="Passwd"]',
    'input[name="password"]',
    'input[autocomplete="current-password"]',
    'input[autocomplete="new-password"]',
    '#password input',
    'input[aria-label="Enter your password"]',
]

# ── "Next" button (email & password steps) ───────────────────────────────────
NEXT_BUTTON_SELECTORS: list[str] = [
    '#identifierNext',
    '#passwordNext',
    'button:has-text("Next")',
    'div[role="button"]:has-text("Next")',
    'button[jsname="LgbsSe"]',
    'div[jsname="LgbsSe"]',
    # French
    'button:has-text("Suivant")',
    'div[role="button"]:has-text("Suivant")',
    # Spanish
    'button:has-text("Siguiente")',
    # Generic fallback
    'button[type="submit"]',
]

# ── "Continue" / confirm buttons ─────────────────────────────────────────────
CONTINUE_BUTTON_SELECTORS: list[str] = [
    'button:has-text("Continue")',
    'div[role="button"]:has-text("Continue")',
    'button:has-text("Continuer")',  # French
    'button:has-text("Continuar")',  # Spanish
    'button:has-text("Got it")',
    'button:has-text("I agree")',
    'button:has-text("Agree")',
    'button:has-text("Accept")',
    # French equivalents
    'button:has-text("Accepter")',
    'button:has-text("D\'accord")',
]

# ── "Skip" / dismiss buttons ──────────────────────────────────────────────────
SKIP_BUTTON_SELECTORS: list[str] = [
    'button:has-text("Skip")',
    'div[role="button"]:has-text("Skip")',
    'button:has-text("Not now")',
    'button:has-text("No thanks")',
    'button:has-text("Remind me later")',
    # French
    'button:has-text("Ignorer")',
    'button:has-text("Pas maintenant")',
    'button:has-text("Non merci")',
    # Spanish
    'button:has-text("Omitir")',
    'button:has-text("Ahora no")',
]

# ── "Done" / finish buttons ───────────────────────────────────────────────────
DONE_BUTTON_SELECTORS: list[str] = [
    'button:has-text("Done")',
    'div[role="button"]:has-text("Done")',
    # French
    'button:has-text("Terminé")',
    'button:has-text("Terminer")',
    # Spanish
    'button:has-text("Listo")',
    'button:has-text("Hecho")',
]

# ── 2FA / TOTP code input ─────────────────────────────────────────────────────
TOTP_INPUT_SELECTORS: list[str] = [
    'input[id*="totpPin"]',
    'input[name="totpPin"]',
    'input[autocomplete="one-time-code"]',
    'input[aria-label*="code"]',
    'input[type="tel"]',
    'input[inputmode="numeric"]',
]

# ── SMS / phone verification code input ───────────────────────────────────────
SMS_CODE_SELECTORS: list[str] = [
    'input[name="idvPreregisteredPhonePin"]',
    'input[id="idvPreregisteredPhonePin"]',
    'input[autocomplete="one-time-code"]',
    'input[aria-label*="code"]',
    'input[type="tel"]',
]

# ── Recovery email input ───────────────────────────────────────────────────────
RECOVERY_EMAIL_SELECTORS: list[str] = [
    'input[type="email"]',
    'input[name="knowledgePreregisteredEmailResponse"]',
    'input[autocomplete="email"]',
    'input[aria-label*="email"]',
]

# ── Confirm it's you / challenge buttons ──────────────────────────────────────
CONFIRM_IDENTITY_SELECTORS: list[str] = [
    'button:has-text("Confirm")',
    'button:has-text("Verify")',
    'button:has-text("Yes")',
    'button:has-text("Yes, it\\'s me")',
    # French
    'button:has-text("Confirmer")',
    'button:has-text("Oui")',
    # Spanish
    'button:has-text("Confirmar")',
    'button:has-text("Sí")',
]

# ── Error / warning message containers ───────────────────────────────────────
ERROR_MESSAGE_SELECTORS: list[str] = [
    'div[jsname="B34EJ"]',          # Google's standard error container
    'div[aria-live="assertive"]',
    'div[role="alert"]',
    '.o6cuMc',
    '.Ekjuhf',
]

# ── "Try another way" link ────────────────────────────────────────────────────
TRY_ANOTHER_WAY_SELECTORS: list[str] = [
    'button:has-text("Try another way")',
    'div[role="button"]:has-text("Try another way")',
    # French
    'button:has-text("Essayer une autre méthode")',
    # Spanish
    'button:has-text("Probar de otra forma")',
]
