"""
Model Config Loader - Reads model_config.yaml and generates model_info entries.

This module replaces the hardcoded model_info dictionary in bridge_all.py
with a YAML-driven configuration system.

Usage:
    from shared_utils.model_config_loader import load_models
    model_info = load_models()
"""

import yaml
import os
from pathlib import Path
from loguru import logger


def _resolve_api_key(api_key_env: str) -> str:
    """Resolve API key from environment variable."""
    key = os.environ.get(api_key_env, "")
    if not key:
        # Fallback: check config.py style names
        from toolbox import get_conf
        try:
            key = get_conf(api_key_env)
        except:
            pass
    return key


def _get_tokenizer():
    """Get GPT tokenizers (reused from bridge_all)."""
    import tiktoken
    from functools import lru_cache

    class LazyloadTiktoken:
        def __init__(self, model):
            self.model = model

        @staticmethod
        @lru_cache(maxsize=128)
        def get_encoder(model):
            logger.info('Loading tokenizer, may download on first run')
            return tiktoken.encoding_for_model(model)

        def encode(self, *args, **kwargs):
            return self.get_encoder(self.model).encode(*args, **kwargs)

        def decode(self, *args, **kwargs):
            return self.get_encoder(self.model).decode(*args, **kwargs)

    return LazyloadTiktoken("gpt-4")


def _create_openai_compatible_bridge(model_conf: dict, tokenizer, token_cnt):
    """Create bridge functions for OpenAI-compatible APIs."""
    from request_llms.oai_std_model_template import get_predict_function

    api_key_conf_name = model_conf["api_key_env"]
    try:
        fn_noui, fn_ui = get_predict_function(
            api_key_conf_name=api_key_conf_name,
            max_output_token=model_conf.get("max_output", 4096),
            disable_proxy=False,
        )
        return fn_ui, fn_noui
    except Exception as e:
        logger.warning(f"Failed to create bridge for {model_conf['name']}: {e}")
        return None, None


def _build_model_info_entry(model_conf: dict, tokenizer, token_cnt) -> dict:
    """Build a single model_info entry from YAML config."""
    name = model_conf["name"]
    provider = model_conf["provider"]

    entry = {
        "max_token": model_conf.get("max_context", 4096),
        "tokenizer": tokenizer,
        "token_cnt": token_cnt,
    }

    # Optional fields
    for opt in ["can_multi_thread", "has_multimodal_capacity", "enable_reasoning"]:
        if opt in model_conf:
            entry[opt] = model_conf[opt]

    if "extra_body" in model_conf:
        entry["extra_body"] = model_conf["extra_body"]

    if "description" in model_conf:
        entry["description"] = model_conf["description"]

    if "base_url" in model_conf:
        entry["endpoint"] = model_conf["base_url"]

    # Create bridge functions based on provider type
    if provider == "openai_compatible":
        fn_ui, fn_noui = _create_openai_compatible_bridge(model_conf, tokenizer, token_cnt)
        if fn_ui:
            entry["fn_with_ui"] = fn_ui
            entry["fn_without_ui"] = fn_noui
    elif provider == "google_gemini":
        from request_llms.bridge_google_gemini import (
            predict as genai_ui,
            predict_no_ui_long_connection as genai_noui,
        )
        entry["fn_with_ui"] = genai_ui
        entry["fn_without_ui"] = genai_noui
    elif provider == "zhipu":
        from request_llms.bridge_zhipu import (
            predict_no_ui_long_connection as zhipu_noui,
            predict as zhipu_ui,
        )
        entry["fn_with_ui"] = zhipu_ui
        entry["fn_without_ui"] = zhipu_noui
    elif provider == "qwen_dashscope":
        from request_llms.bridge_qwen import (
            predict_no_ui_long_connection as qwen_noui,
            predict as qwen_ui,
        )
        entry["fn_with_ui"] = qwen_ui
        entry["fn_without_ui"] = qwen_noui
    elif provider == "anthropic":
        from request_llms.bridge_claude import (
            predict as claude_ui,
            predict_no_ui_long_connection as claude_noui,
        )
        entry["fn_with_ui"] = claude_ui
        entry["fn_without_ui"] = claude_noui
    elif provider == "cohere":
        from request_llms.bridge_cohere import (
            predict as cohere_ui,
            predict_no_ui_long_connection as cohere_noui,
        )
        entry["fn_with_ui"] = cohere_ui
        entry["fn_without_ui"] = cohere_noui

    return {name: entry}


def load_models(config_path: str = None) -> dict:
    """
    Load model configurations from model_config.yaml.

    Returns:
        dict: model_info dictionary compatible with bridge_all.py format.
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "model_config.yaml"

    if not os.path.exists(config_path):
        logger.warning(f"model_config.yaml not found at {config_path}, skipping YAML model loading")
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load model_config.yaml: {e}")
        return {}

    if not config or "models" not in config:
        logger.warning("model_config.yaml has no 'models' section")
        return {}

    tokenizer = _get_tokenizer()
    token_cnt = lambda txt: len(tokenizer.encode(txt, disallowed_special=()))

    model_info = {}
    for model_conf in config["models"]:
        try:
            entry = _build_model_info_entry(model_conf, tokenizer, token_cnt)
            model_info.update(entry)
            logger.info(f"Loaded model: {model_conf['name']} ({model_conf['provider']})")
        except Exception as e:
            logger.error(f"Failed to load model {model_conf.get('name', 'unknown')}: {e}")
            continue

    return model_info


def get_default_model(config_path: str = None) -> str:
    """Get the default model from model_config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "model_config.yaml"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("default_model", "gpt-3.5-turbo")
    except:
        return "gpt-3.5-turbo"


def get_available_models(config_path: str = None) -> list:
    """Get list of available model names from model_config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "model_config.yaml"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return [m["name"] for m in config.get("models", [])]
    except:
        return []
