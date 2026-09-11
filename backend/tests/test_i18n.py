from app.core.i18n import negotiate_locale, t


def test_negotiation_prefers_explicit_then_header():
    assert negotiate_locale("fr-CA,fr;q=0.9,en;q=0.8") == "fr"
    assert negotiate_locale("de-DE,de;q=0.9") == "en"
    assert negotiate_locale("de", preferred="fr") == "fr"


def test_translations_exist_in_both_locales():
    assert t("errors.not_authenticated", "en") != t("errors.not_authenticated", "fr")
    assert t("milestones.artist_streams", "fr", entity="Daft Punk", value=500) == "Daft Punk écouté 500 fois"


def test_missing_key_falls_back_to_key():
    assert t("nope.missing", "fr") == "nope.missing"
