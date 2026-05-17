from app.core.config import Settings


INSECURE_SECRET_VALUES = {
    "",
    "change-me-in-production",
    "please-change-this-secret",
    "replace-with-random-secret-at-least-32-chars",
}
INSECURE_ADMIN_PASSWORDS = {
    "",
    "admin",
    "admin123456",
    "password",
    "replace-with-strong-password",
}
INSECURE_SUBSCRIPTION_TOKENS = {
    "",
    "nebula-sub-token",
    "replace-with-random-token-at-least-24-chars",
}


class StartupCheckError(RuntimeError):
    pass


def validate_startup_settings(settings: Settings) -> None:
    if settings.APP_ENV.lower() != "production" or settings.ALLOW_INSECURE_DEFAULTS:
        return

    problems: list[str] = []
    if settings.SECRET_KEY in INSECURE_SECRET_VALUES or len(settings.SECRET_KEY) < 32:
        problems.append("SECRET_KEY must be changed to a random value of at least 32 characters")
    if settings.ADMIN_PASSWORD in INSECURE_ADMIN_PASSWORDS or len(settings.ADMIN_PASSWORD) < 12:
        problems.append("ADMIN_PASSWORD must be changed to a strong password of at least 12 characters")
    if settings.SUBSCRIPTION_TOKEN in INSECURE_SUBSCRIPTION_TOKENS or len(settings.SUBSCRIPTION_TOKEN) < 24:
        problems.append("SUBSCRIPTION_TOKEN must be changed to a random value of at least 24 characters")

    if problems:
        detail = "; ".join(problems)
        raise StartupCheckError(
            f"Refusing to start in production with insecure defaults: {detail}. "
            "Set strong values in .env, or set ALLOW_INSECURE_DEFAULTS=true only for trusted local testing."
        )
