import os
import yaml


def load_config(env: str = "dev") -> dict:
    config_dir = os.path.dirname(__file__)

    with open(os.path.join(config_dir, "common.yml")) as f:
        config = yaml.safe_load(f)

    env_file = os.path.join(config_dir, f"{env}.yml")
    if os.path.exists(env_file):
        with open(env_file) as f:
            env_config = yaml.safe_load(f) or {}
        _deep_merge(config, env_config)

    return config


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
