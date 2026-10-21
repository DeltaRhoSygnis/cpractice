"""Provider resolution: any credential the operator has must be usable.

The application must not be limited to one hard-coded credential name. The
selected provider wins when its credential is present; otherwise any provider
holding a credential is used, and the model always belongs to the provider
that will actually be called.
"""

from __future__ import annotations

import pytest

from app.config import AI_PROVIDERS, Settings


def _settings(**overrides) -> Settings:
    values = {
        "database_path": "data/cpractice.db",
        "problems_dir": "problems",
        "workspaces_dir": "workspaces",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_no_credential_means_offline() -> None:
    settings = _settings()

    assert settings.any_ai_key_configured is False
    assert settings.resolved_ai_provider is None


def test_selected_provider_wins_when_its_credential_is_present() -> None:
    settings = _settings(ai_provider="kenari", kenari_api_key="kn-secret")

    assert settings.resolved_ai_provider == "kenari"
    assert settings.any_ai_key_configured is True


def test_any_credential_is_used_when_the_selected_provider_has_none() -> None:
    """A machine holding only a Google key must still get a working pipeline."""
    settings = _settings(ai_provider="kenari", google_api_key="goog-secret")

    assert settings.resolved_ai_provider == "google"
    assert settings.any_ai_key_configured is True


def test_resolved_model_belongs_to_the_resolved_provider() -> None:
    settings = _settings(ai_provider="kenari", google_api_key="goog-secret")

    assert settings.resolved_ai_model == AI_PROVIDERS["google"].default_model


def test_explicit_model_is_never_overridden() -> None:
    settings = _settings(
        ai_provider="kenari",
        google_api_key="goog-secret",
        ai_model="gemini-2.5-pro",
    )

    assert settings.resolved_ai_model == "gemini-2.5-pro"


def test_unknown_provider_has_no_credential() -> None:
    settings = _settings(ai_provider="nonexistent")

    assert settings.ai_key_for("nonexistent") is None
    assert settings.resolved_ai_provider is None


def test_every_registered_provider_is_reachable_by_its_own_key() -> None:
    """Each registered provider must be usable with only its own credential."""
    for name, spec in AI_PROVIDERS.items():
        settings = _settings(**{spec.key_field: "secret-for-" + name})

        assert settings.resolved_ai_provider == name
        assert settings.resolved_ai_model == spec.default_model


@pytest.mark.parametrize("provider", sorted(AI_PROVIDERS))
def test_credential_values_are_never_echoed(provider: str) -> None:
    """Resolution must not leak the credential value anywhere."""
    settings = _settings(ai_provider=provider, **{AI_PROVIDERS[provider].key_field: "kn-secret"})

    assert "kn-secret" not in repr(settings.resolved_ai_provider)
    assert "kn-secret" not in settings.resolved_ai_model
