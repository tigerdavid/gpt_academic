"""
Model Config Hot Reload - Reload model_config.yaml without restarting.

Click the button to refresh model list from YAML config.
"""

from toolbox import update_ui, report_exception
from loguru import logger


def 刷新模型配置(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """Hot-reload model_config.yaml and update model_info + AVAIL_LLM_MODELS."""
    try:
        from shared_utils.model_config_loader import load_models, get_available_models
        from request_llms.bridge_all import model_info, AVAIL_LLM_MODELS

        # Reload YAML models
        yaml_models = load_models()
        if not yaml_models:
            chatbot.append(["刷新模型配置", "❌ model_config.yaml 未找到或为空"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        # Update model_info (merge, YAML takes priority)
        model_info.update(yaml_models)

        # Update AVAIL_LLM_MODELS
        for name in yaml_models.keys():
            if name not in AVAIL_LLM_MODELS:
                AVAIL_LLM_MODELS.append(name)

        lines = ["## ✅ 模型配置已刷新\n"]
        lines.append(f"从 model_config.yaml 加载了 **{len(yaml_models)}** 个模型：\n")
        for name in sorted(yaml_models.keys()):
            lines.append(f"- `{name}`")

        lines.append(f"\n💡 刷新页面后下拉菜单会更新。")

        chatbot.append(["刷新模型配置", "\n".join(lines)])
        yield from update_ui(chatbot=chatbot, history=history)

    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))


def Token统计(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """Display current session token usage and cost summary."""
    try:
        from shared_utils.token_cost_tracker import get_tracker

        tracker = get_tracker()
        summary = tracker.get_summary()

        if not summary:
            chatbot.append(["Token统计", "📭 当前会话还没有 API 请求记录。"])
        else:
            chatbot.append(["Token统计", summary])

        yield from update_ui(chatbot=chatbot, history=history)

    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))
