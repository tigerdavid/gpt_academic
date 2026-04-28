"""
AI Settings Assistant - Natural language configuration management.
Type what you want to change and it happens automatically.
"""

import os
import json
import shutil
from toolbox import update_ui, report_exception, get_conf
from loguru import logger

# Config paths
CONFIG_PRIVATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config_private.py')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.py')
MODEL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'model_config.yaml')

SETTINGS_SYSTEM_PROMPT = """你是一个 GPT Academic 配置助手。你可以修改软件配置来实现用户的需求。

## 可修改的配置项：

| 配置项 | 说明 | 可选值 |
|--------|------|--------|
| LLM_MODEL | 默认模型 | deepseek-v4-pro, deepseek-v4-flash, gpt-4o, claude-sonnet-4-6 等 |
| API_KEY | API密钥 | 任意字符串 |
| SIMPLE_UI | 简洁模式 | True/False |
| THEME | 主题 | default, green, contrast, gradios |
| AUTO_CLEAR_TXT | 自动清空输入 | True/False |
| WEB_PORT | 端口号 | 数字(1024-65535) |
| DEFAULT_FN_GROUPS | 默认插件组 | ['对话', '学术', '编程', '智能体'] 的子集 |
| DARK_MODE | 暗色模式 | True/False |
| LAYOUT | 布局 | LEFT-RIGHT, LEFT-UP |
| TOKEN_LIMIT | Token上限 | 数字(1024-32768) |
| USE_PROXY | 使用代理 | True/False |

## 你的能力：
1. 理解用户自然语言指令，识别要修改的配置
2. 读取当前 `config_private.py` 配置
3. 修改配置并保存
4. 告知用户修改了什么，以及是否需要重启生效

## 回复格式：
每次修改完成后，用简洁的 Markdown 表格展示修改前后的对比。
"""


def _read_config_private():
    """Read current config_private.py contents."""
    if not os.path.exists(CONFIG_PRIVATE_PATH):
        return "# 配置文件不存在"
    with open(CONFIG_PRIVATE_PATH, 'r') as f:
        return f.read()


def _write_config_private(content):
    """Write config_private.py with backup."""
    if os.path.exists(CONFIG_PRIVATE_PATH):
        backup = CONFIG_PRIVATE_PATH + '.backup'
        shutil.copy2(CONFIG_PRIVATE_PATH, backup)
    with open(CONFIG_PRIVATE_PATH, 'w') as f:
        f.write(content)
    return True


def _apply_setting(key, value):
    """Apply a single setting change to config_private.py."""
    content = _read_config_private()
    old_value = None
    
    # Python literal format
    if isinstance(value, bool):
        val_str = str(value)
    elif isinstance(value, list):
        val_str = str(value)
    elif isinstance(value, str):
        val_str = f'"{value}"'
    elif isinstance(value, (int, float)):
        val_str = str(value)
    else:
        val_str = str(value)
    
    import re
    pattern = rf'^{key}\s*=\s*.*$'
    new_line = f'{key} = {val_str}'
    
    new_content = []
    found = False
    for line in content.split('\n'):
        if re.match(pattern, line):
            # Extract old value
            old_match = re.match(rf'^{key}\s*=\s*(.*)$', line)
            if old_match:
                old_value = old_match.group(1).strip().rstrip('#').strip()
            new_content.append(new_line + '  # AI设置助手修改')
            found = True
        else:
            new_content.append(line)
    
    if not found:
        # Append at end
        new_content.append('')
        new_content.append(f'# AI设置助手自动添加')
        new_content.append(new_line)
    
    _write_config_private('\n'.join(new_content))
    return old_value


def _get_all_settings():
    """Get a summary of current settings."""
    settings = {}
    keys = ['LLM_MODEL', 'WEB_PORT', 'SIMPLE_UI', 'THEME', 'LAYOUT', 
            'AUTO_CLEAR_TXT', 'DARK_MODE', 'DEFAULT_FN_GROUPS', 'USE_PROXY',
            'CHATBOT_HEIGHT', 'CONCURRENT_COUNT']
    for key in keys:
        try:
            val = get_conf(key)
            settings[key] = val
        except:
            settings[key] = '(未配置)'
    return settings


def AI设置助手(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """
    AI Settings Assistant - natural language config management.
    Activates when user types commands like:
    - 把模型改成xxx
    - 开启/关闭简洁模式
    - 查看当前配置
    - 修改主题为xxx
    """
    import re
    
    if not txt or not txt.strip():
        chatbot.append(["AI设置", "请描述你想修改的配置，例如：\n- `查看当前配置`\n- `把模型改成 deepseek-v4-flash`\n- `开启简洁模式`\n- `修改主题为 green`"])
        yield from update_ui(chatbot=chatbot, history=history)
        return

    command = txt.strip()
    response_parts = []
    
    # --- COMMAND: 查看配置 ---
    if any(w in command for w in ['查看', '当前配置', '显示配置', '配置是什么', 'settings', 'status']):
        settings = _get_all_settings()
        lines = ["## ⚙️ 当前配置\n"]
        lines.append("| 配置项 | 值 |")
        lines.append("|--------|-----|")
        for k, v in settings.items():
            if isinstance(v, list):
                v = ', '.join(v)
            lines.append(f"| {k} | `{v}` |")
        chatbot.append([f"查看配置", "\n".join(lines)])
        yield from update_ui(chatbot=chatbot, history=history)
        return
    
    # --- COMMAND: 切换模型 ---
    if any(w in command for w in ['模型', 'model', 'LLM']):
        # Extract model name
        model_names = ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner',
                       'gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'o4-mini', 'o3',
                       'claude-sonnet-4-6', 'claude-haiku-4-5', 'claude-opus-4-6',
                       'gemini-2.0-flash', 'gemini-2.5-pro', 'qwen-max', 'glm-4', 'moonshot-v1-128k']
        found = None
        for name in model_names:
            if name in command:
                found = name
                break
        if found:
            old = _apply_setting('LLM_MODEL', found)
            chatbot.append(["修改模型", f"✅ 默认模型已从 `{old}` 改为 **`{found}`**\n\n⚠️ 需要重启生效。"])
        else:
            chatbot.append(["修改模型", f"🤔 请指定模型名称，例如：`把模型改成 deepseek-v4-flash`\n\n可用：{', '.join(model_names[:6])}... 等"])
        yield from update_ui(chatbot=chatbot, history=history)
        return
    
    # --- COMMAND: 简洁模式 ---
    if any(w in command for w in ['简洁', 'simple', 'SIMPLE']):
        if any(w in command for w in ['开启', '打开', 'true', 'True', '启用', '打开简洁', '开启简洁']):
            _apply_setting('SIMPLE_UI', True)
            chatbot.append(["简洁模式", "✅ 简洁模式已**开启**\n\n插件区和顶部帮助文字将被折叠。刷新页面生效。"])
        else:
            _apply_setting('SIMPLE_UI', False)
            chatbot.append(["简洁模式", "✅ 简洁模式已**关闭**\n\n所有插件和帮助文字将恢复显示。刷新页面生效。"])
        yield from update_ui(chatbot=chatbot, history=history)
        return
    
    # --- COMMAND: 主题 ---
    if any(w in command for w in ['主题', 'theme', '颜色']):
        themes = ['default', 'green', 'contrast', 'gradios']
        found = None
        for t in themes:
            if t in command:
                found = t
                break
        if found:
            old = _apply_setting('THEME', found)
            chatbot.append(["修改主题", f"✅ 主题已从 `{old}` 改为 **`{found}`**\n\n刷新页面生效。"])
        else:
            chatbot.append(["修改主题", f"可用主题：`default`, `green`, `contrast`, `gradios`\n请指定一个，例如：`主题换成 green`"])
        yield from update_ui(chatbot=chatbot, history=history)
        return
    
    # --- COMMAND: 暗色模式 ---
    if any(w in command for w in ['暗色', '暗黑', 'dark', '夜间']):
        if any(w in command for w in ['开启', '打开', 'true', '启用']):
            _apply_setting('DARK_MODE', True)
            chatbot.append(["暗色模式", "✅ 暗色模式已**开启**，刷新页面生效。"])
        else:
            _apply_setting('DARK_MODE', False)
            chatbot.append(["暗色模式", "✅ 暗色模式已**关闭**，刷新页面生效。"])
        yield from update_ui(chatbot=chatbot, history=history)
        return
    
    # --- COMMAND: 代理 ---
    if any(w in command for w in ['代理', 'proxy', 'PROXY']):
        if any(w in command for w in ['开启', '打开', 'true', '启用']):
            _apply_setting('USE_PROXY', True)
            chatbot.append(["代理设置", "✅ 代理已**开启**，重启生效。"])
        else:
            _apply_setting('USE_PROXY', False)
            chatbot.append(["代理设置", "✅ 代理已**关闭**，重启生效。"])
        yield from update_ui(chatbot=chatbot, history=history)
        return
    
    # --- Fallback ---
    settings = _get_all_settings()
    chatbot.append(["AI设置", f"""🤔 我没有理解你的指令。

## 当前配置
| 配置项 | 值 |
|--------|-----|
| LLM_MODEL | `{settings.get('LLM_MODEL', '?')}` |
| THEME | `{settings.get('THEME', '?')}` |
| SIMPLE_UI | `{settings.get('SIMPLE_UI', '?')}` |
| DARK_MODE | `{settings.get('DARK_MODE', '?')}` |
| USE_PROXY | `{settings.get('USE_PROXY', '?')}` |

## 试试这些指令：
- `查看当前配置` - 显示所有设置
- `把模型改成 deepseek-v4-flash` - 切换默认模型
- `开启简洁模式` / `关闭简洁模式`
- `主题换成 green` - 换颜色主题
- `开启暗色模式` / `关闭暗色模式`
- `开启代理` / `关闭代理`
"""])
    yield from update_ui(chatbot=chatbot, history=history)
