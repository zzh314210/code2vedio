import copy
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from configuration import DEFAULTS, load_config, merge, public_config, resolve_config, sanitize_error


def check():
    original_defaults = copy.deepcopy(DEFAULTS)
    defaults = resolve_config({})
    assert defaults["tts"]["provider"] == "edge"
    assert defaults["vision"]["enabled"] is False
    assert defaults["video"] == DEFAULTS["video"]
    assert resolve_config(defaults) == defaults
    first = resolve_config({
        "text": {"base_url": "https://first.example/v1", "api_key": "fake-first-secret",
                 "model": "first", "extra_body": {"nested": {"shared": 1, "changed": 1}}},
        "vision": {"extra_body": {"nested": {"changed": 9}}},
        "tts": {"provider": "openai"},
        "course": {"language": "first", "prompts": {"outline": "old", "review": "old"}},
        "task": {"prompts": {"review": "explicit"}},
    })
    assert resolve_config(first) == first
    updated = merge(first, {
        "text": {"base_url": "https://second.example/v1", "api_key": "fake-second-secret",
                 "model": "second", "extra_body": {"nested": {"shared": 2, "changed": 2}}},
        "course": {"language": "second", "prompts": {"outline": "new", "review": "new"}},
    })
    second = resolve_config(updated)
    for role in ("vision", "tts"):
        for key in ("base_url", "api_key"):
            assert second[role][key] == second["text"][key], (role, key)
    assert second["vision"]["model"] == "second"
    assert second["vision"]["extra_body"]["nested"] == {"shared": 2, "changed": 9}
    assert second["task"]["language"] == "second"
    assert second["task"]["prompts"] == {"outline": "new", "review": "explicit"}
    assert resolve_config(second) == second
    assert first["vision"]["base_url"] == "https://first.example/v1"
    direct = copy.deepcopy(first)
    direct["text"]["base_url"] = "https://direct.example/v1"
    direct["vision"]["model"] = "independent"
    direct["course"]["language"] = "direct"
    direct = resolve_config(direct)
    assert direct["vision"]["base_url"] == direct["text"]["base_url"]
    assert direct["vision"]["model"] == "independent"
    assert direct["task"]["language"] == "direct"
    explicit = resolve_config(merge(first, {
        "vision": {"inherit_text": False, "base_url": "https://vision.example/v1",
                   "api_key": "fake-vision-secret", "model": "vision"},
        "tts": {"base_url": "https://tts.example/v1", "api_key": "fake-tts-secret"},
    }))
    independent = resolve_config(merge(explicit, {"text": {"base_url": "https://third.example/v1",
                                                          "api_key": "fake-third-secret"}}))
    assert independent["vision"] == explicit["vision"]
    assert independent["tts"] == explicit["tts"]
    partial = resolve_config(merge(first, {
        "vision": {"inherit_text": True, "model": "explicit-vision",
                   "api_key": "fake-independent-secret"},
        "tts": {"base_url": "https://independent-tts.example/v1"},
    }))
    partial = resolve_config(merge(partial, {"text": {
        "base_url": "https://changed.example/v1", "api_key": "fake-changed-secret",
        "model": "changed", "protocol": "chat_completions",
    }}))
    assert partial["vision"]["base_url"] == partial["text"]["base_url"]
    assert partial["vision"]["protocol"] == "chat_completions"
    assert partial["vision"]["model"] == "explicit-vision"
    assert partial["vision"]["api_key"] == "fake-independent-secret"
    assert partial["tts"]["base_url"] == "https://independent-tts.example/v1"
    assert partial["tts"]["api_key"] == "fake-changed-secret"
    same_value = resolve_config(merge(first, {
        "vision": {"base_url": first["text"]["base_url"]},
        "tts": {"api_key": first["text"]["api_key"]},
        "task": {"language": first["course"]["language"]},
    }))
    same_value = resolve_config(merge(same_value, {
        "text": {"base_url": "https://new.example/v1", "api_key": "fake-new-secret"},
        "course": {"language": "new"},
    }))
    assert same_value["vision"]["base_url"] == first["text"]["base_url"]
    assert same_value["tts"]["api_key"] == first["text"]["api_key"]
    assert same_value["task"]["language"] == "first"
    blank = resolve_config(merge(second, {"vision": {"base_url": ""}, "tts": {"api_key": None}}))
    assert blank["vision"]["base_url"] == second["text"]["base_url"]
    assert blank["tts"]["api_key"] == second["text"]["api_key"]
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / "synthetic.json"
        filename.write_text(json.dumps({"tts": {"provider": "openai"},
                                        "text": {"api_key": "${CONFIG_SMOKE_KEY}"}}), encoding="utf-8")
        with patch("configuration.load_dotenv") as dotenv, patch.dict("os.environ", {"CONFIG_SMOKE_KEY": "fake-env-secret"}, clear=True):
            loaded = load_config(filename)
            assert loaded["tts"]["api_key"] == "fake-env-secret"
            assert dotenv.call_count == 1
            raw = load_config(filename, resolved=False)
            assert raw["text"]["api_key"] == "${CONFIG_SMOKE_KEY}"
            assert resolve_config(raw) == loaded
            loaded = resolve_config(merge(loaded, {"text": {"api_key": "fake-new-secret"}}))
            assert loaded["tts"]["api_key"] == "fake-new-secret"
    secret_config = merge(second, {"credentials": {"password": "fake-password-secret"},
                                   "extra": [{"headers": {"Authorization": "Bearer fake-header-secret"}}]})
    serialized = json.dumps(secret_config)
    assert "_inherited" not in serialized
    redacted = json.dumps(public_config(secret_config))
    error = sanitize_error("fake-second-secret fake-password-secret Bearer fake-header-secret", secret_config)
    for secret in ("fake-second-secret", "fake-password-secret", "fake-header-secret"):
        assert secret not in redacted
        assert secret not in error
    assert DEFAULTS == original_defaults
    print("config smoke passed: defaults, repeated resolution, nested inheritance, explicit overrides, task/course, redaction")


if __name__ == "__main__":
    check()
