"""
Conversation Manager Plugin - Manage saved conversations from the Gradio UI.

Provides:
- List saved conversations
- Load a saved conversation
- Delete conversations
- Export conversation to Markdown
"""

from toolbox import update_ui, CatchException, report_exception
from crazy_functions.crazy_utils import request_gpt_model_in_new_thread_with_ui_alive


def 对话管理(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """列出所有已保存的对话"""
    try:
        from shared_utils.conv_auto_save import get_saved_conversations
        conversations = get_saved_conversations(limit=50)

        if not conversations:
            chatbot.append(["对话管理", "📭 没有已保存的对话。\n\n在对话区发送消息后会自动保存。"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        lines = ["## 📋 已保存的对话\n"]
        for i, conv in enumerate(conversations, 1):
            pinned = "📌 " if conv.get("is_pinned") else ""
            lines.append(f"{i}. {pinned}**{conv['title']}**")
            lines.append(f"   - ID: `{conv['id']}`")
            lines.append(f"   - Model: {conv['model']} | Messages: {conv['message_count']}")
            lines.append(f"   - Created: {conv['created_at_str']} | Updated: {conv['updated_at_str']}")
            lines.append("")

        lines.append("\n💡 使用说明：")
        lines.append("- 输入对话ID可加载该对话：`load:conv_xxxxx`")
        lines.append("- 输入 `delete:conv_xxxxx` 删除对话")
        lines.append("- 输入 `export:conv_xxxxx` 导出对话为 Markdown")
        lines.append("- 输入 `start` 开始新对话")

        chatbot.append(["对话管理", "\n".join(lines)])
        yield from update_ui(chatbot=chatbot, history=history)
    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))


def 加载对话(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """加载一个已保存的对话"""
    try:
        from shared_utils.conv_auto_save import load_conversation_messages, get_current_conv_id

        conv_id = txt.strip()
        if conv_id.startswith("load:"):
            conv_id = conv_id[5:].strip()

        messages = load_conversation_messages(conv_id)
        if not messages:
            chatbot.append([f"加载对话 {conv_id}", "❌ 对话不存在或已删除"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        # Convert to history format
        new_history = []
        for msg in messages:
            new_history.append(msg["content"])

        chatbot.clear()
        chatbot.append([f"加载对话 {conv_id}", f"✅ 已加载，共 {len(messages)} 条消息"])
        yield from update_ui(chatbot=chatbot, history=new_history)
    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))


def 删除对话(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """删除一个已保存的对话"""
    try:
        from shared_utils.conv_auto_save import delete_current_conversation, get_saved_conversations
        from shared_utils.conversation_store import delete_conversation

        conv_id = txt.strip()
        if conv_id.startswith("delete:"):
            conv_id = conv_id[5:].strip()

        delete_conversation(conv_id)
        chatbot.append([f"删除对话 {conv_id}", "✅ 对话已删除"])
        yield from update_ui(chatbot=chatbot, history=history)
    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))


def 导出对话(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """导出对话为 Markdown"""
    try:
        from shared_utils.conversation_store import export_conversation_markdown

        conv_id = txt.strip()
        if conv_id.startswith("export:"):
            conv_id = conv_id[5:].strip()

        md_content = export_conversation_markdown(conv_id)
        if not md_content:
            chatbot.append([f"导出对话 {conv_id}", "❌ 对话不存在"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        # Save to file
        import os
        export_dir = "gpt_log/conversations"
        os.makedirs(export_dir, exist_ok=True)
        filepath = f"{export_dir}/{conv_id}.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        chatbot.append([f"导出对话 {conv_id}", f"✅ 已导出到 `{filepath}`"])
        yield from update_ui(chatbot=chatbot, history=history)
    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))


def 开始新对话(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """开始一个新的对话"""
    try:
        from shared_utils.conv_auto_save import start_conversation

        conv_id = start_conversation(model=llm_kwargs.get("llm_model", "unknown"))
        chatbot.clear()
        chatbot.append(["开始新对话", f"✅ 新对话已创建 `{conv_id}`"])
        yield from update_ui(chatbot=chatbot, history=[])
    except Exception as e:
        report_exception(chatbot, history, str(e), str(e))
