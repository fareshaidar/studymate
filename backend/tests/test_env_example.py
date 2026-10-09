"""backend/.env.example: no key, and every value is the code's current default.

Only the template is read; the real backend/.env is never opened.
"""

import re
from pathlib import Path

from app.config import Settings

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
# An active "NAME=value" line, or a commented-out "# NAME=value" one.
SETTING_LINE = re.compile(r"^(?:#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def settings_in_example() -> dict[str, str]:
    found = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = SETTING_LINE.match(line.strip())
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


def test_the_template_holds_no_key():
    text = EXAMPLE.read_text(encoding="utf-8")

    assert settings_in_example()["GEMINI_API_KEY"] == ""
    assert "AIza" not in text  # how Google API keys start


def test_every_name_is_a_real_setting():
    fields = {name.upper() for name in Settings.model_fields}

    assert set(settings_in_example()) <= fields


def test_every_setting_is_listed():
    fields = {name.upper() for name in Settings.model_fields}

    assert set(settings_in_example()) == fields


def test_every_value_is_the_current_default():
    for name, text in settings_in_example().items():
        field = name.lower()
        # The default written in config.py, not a Settings() instance: an instance would
        # also read environment variables (a real key could then show up in a failure).
        default = Settings.model_fields[field].default
        # Let the settings class parse the text (e.g. "false", "0.55", "data") like it would
        # from .env; a keyword argument wins over any environment variable.
        parsed = getattr(Settings(_env_file=None, **{field: text}), field)
        assert parsed == default, f"{name} in .env.example is not the code default"
