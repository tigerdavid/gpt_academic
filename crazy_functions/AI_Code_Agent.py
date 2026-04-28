"""
AI Code Agent - Natural language code modification and feature creation.

Chat with the AI to:
- Add new features and plugins
- Modify existing code
- Change configuration
- Fix bugs
- Create custom functions

The AI has access to the project filesystem and can write code, register plugins,
commit to git, and restart the app.
"""

import os
import re
import json
import subprocess
import shutil
import traceback
from toolbox import update_ui, report_exception, get_conf
from loguru import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AGENT_SYSTEM_PROMPT = """你是 GPT Academic 的 AI 代码助手。你可以通过对话直接修改这个应用的功能和代码。

## 项目结构
- `main.py` - 主程序入口，Gradio UI 定义
- `config.py` - 全局配置
- `config_private.py` - 私有配置（API Key 等敏感信息）
- `model_config.yaml` - 模型配置 YAML
- `crazy_functions/` - 插件目录，每个插件一个 .py 文件
- `crazy_functional.py` - 插件注册中心
- `shared_utils/` - 共享工具模块

## 你可以使用的工具（回复时用```json代码块，每次只调用一个）

read_file     - 读取文件内容  {"tool":"read_file","path":"crazy_functions/xxx.py"}
write_file    - 创建/覆盖文件 {"tool":"write_file","path":"crazy_functions/New.py","content":"文件内容"}
edit_file     - 替换文件内容  {"tool":"edit_file","path":"config.py","old":"旧文本","new":"新文本"}
set_config    - 修改配置     {"tool":"set_config","key":"LLM_MODEL","value":"deepseek-v4-pro"}
register_plugin - 注册插件   {"tool":"register_plugin","name":"功能名","group":"对话","info":"描述","filename":"PluginFile"}
shell         - 执行命令     {"tool":"shell","command":"git status"}
git_commit    - 提交代码     {"tool":"git_commit","message":"feat: xxx"}

## 规则
- 每次只调用一个工具
- 用中文回复
- 改 Python 文件后确保语法正确
- 完成后调用 git_commit
"""


def _parse_tool_call(text):
    """Parse a tool call from LLM response."""
    json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if not json_match:
        json_match = re.search(r'\{[^{}]*"tool"\s*:\s*"[^"]+"[^{}]*\}', text, re.DOTALL)
    
    if json_match:
        try:
            data = json.loads(json_match.group(1) if json_match.lastindex else json_match.group(0))
            if "tool" in data:
                tool = data.pop("tool")
                return tool, data
        except (json.JSONDecodeError, AttributeError):
            pass
    return None, None


def _execute_tool(tool_name, params):
    """Execute a tool call."""
    if tool_name == "read_file":
        path = os.path.join(PROJECT_ROOT, params.get("path", ""))
        if not os.path.exists(path):
            return f"文件不存在: {path}"
        if not path.startswith(PROJECT_ROOT):
            return "安全限制：不能读取项目外文件"
        with open(path, 'r') as f:
            content = f.read()
        max_chars = int(params.get("max_chars", 8000))
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (截断，共 {len(content)} 字符)"
        return content

    elif tool_name == "write_file":
        path = os.path.join(PROJECT_ROOT, params.get("path", ""))
        content = params.get("content", "")
        if not path.startswith(PROJECT_ROOT):
            return "安全限制：只能在项目内创建"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            shutil.copy2(path, path + '.agent_backup')
        with open(path, 'w') as f:
            f.write(content)
        if path.endswith('.py'):
            try:
                import ast; ast.parse(content)
                return f"已创建并验证通过: {params['path']} ({len(content)} 字符)"
            except SyntaxError as e:
                return f"文件已写入但有语法错误: {e}"
        return f"已创建: {params['path']} ({len(content)} 字符)"

    elif tool_name == "edit_file":
        path = os.path.join(PROJECT_ROOT, params.get("path", ""))
        old_text = params.get("old", "")
        new_text = params.get("new", "")
        if not path.startswith(PROJECT_ROOT):
            return "安全限制：只能在项目内编辑"
        if not os.path.exists(path):
            return f"文件不存在: {path}"
        with open(path, 'r') as f:
            content = f.read()
        if old_text not in content:
            return f"未找到要替换的文本。前50字符: {old_text[:50]}"
        shutil.copy2(path, path + '.agent_backup')
        content = content.replace(old_text, new_text, 1)
        with open(path, 'w') as f:
            f.write(content)
        return f"已编辑: {params['path']}"

    elif tool_name == "set_config":
        key = params.get("key", "")
        value = params.get("value")
        config_path = os.path.join(PROJECT_ROOT, 'config_private.py')
        if not os.path.exists(config_path):
            config_path = os.path.join(PROJECT_ROOT, 'config.py')
        with open(config_path, 'r') as f:
            content = f.read()
        if isinstance(value, str) and not value.startswith('[') and value not in ('True','False'):
            val_str = f'"{value}"'
        else:
            val_str = str(value)
        pattern = rf'^{key}\s*=\s*.*$'
        new_lines, found = [], False
        for line in content.split('\n'):
            if re.match(pattern, line):
                new_lines.append(f'{key} = {val_str}  # AI修改')
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f'# AI添加\n{key} = {val_str}')
        shutil.copy2(config_path, config_path + '.agent_backup')
        with open(config_path, 'w') as f:
            f.write('\n'.join(new_lines))
        return f"配置已更新: {key} = {value}"

    elif tool_name == "register_plugin":
        name = params.get("name", "")
        group = params.get("group", "对话")
        info = params.get("info", "")
        filename = params.get("filename", "")
        fpath = os.path.join(PROJECT_ROOT, 'crazy_functional.py')
        with open(fpath, 'r') as f:
            content = f.read()
        if f'"{name}"' in content or f"'{name}'" in content:
            return f"插件 {name} 已存在"
        import_line = f'    from crazy_functions.{filename} import {name}\n'
        # Find last import from crazy_functions
        last_import = content.rfind('from crazy_functions.')
        if last_import > 0:
            nl = content.index('\n', last_import)
            content = content[:nl+1] + import_line + content[nl+1:]
        else:
            content = import_line + content
        # Add to function dict
        end_marker = '    })\n'
        plugin_entry = f'''        "{name}": {{
            "Group": "{group}",
            "Color": "primary",
            "AsButton": True,
            "Info": "{info}",
            "Function": HotReload({name}),
        }},\n{end_marker}'''
        content = content.replace(end_marker, plugin_entry, 1)
        shutil.copy2(fpath, fpath + '.agent_backup')
        with open(fpath, 'w') as f:
            f.write(content)
        return f"插件 {name} 已注册到 {group}"

    elif tool_name == "shell":
        cmd = params.get("command", "")
        try:
            r = subprocess.run(cmd, shell=True, cwd=PROJECT_ROOT,
                              capture_output=True, text=True, timeout=30)
            out = (r.stdout + r.stderr)[:2000]
            return out if out else "(无输出)"
        except subprocess.TimeoutExpired:
            return "命令超时"
        except Exception as e:
            return str(e)

    elif tool_name == "git_commit":
        msg = params.get("message", "AI Agent changes")
        try:
            subprocess.run(["git", "add", "-A"], cwd=PROJECT_ROOT,
                          capture_output=True, timeout=10)
            r = subprocess.run(["git", "commit", "-m", msg], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, timeout=10)
            if "nothing to commit" in r.stdout + r.stderr:
                return "没有变更需要提交"
            return f"已提交: {msg}"
        except Exception as e:
            return f"提交失败: {e}"

    else:
        return f"未知工具: {tool_name}"


def _run_agent_loop(user_message, llm_kwargs):
    """Agent loop: LLM -> tool -> LLM -> ... until done."""
    from request_llms.bridge_all import predict_no_ui_long_connection

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"用户需求: {user_message}\n\n请开始执行。每次回复只调用一个工具。"}
    ]

    step_log = []
    for i in range(6):
        try:
            response = predict_no_ui_long_connection(
                inputs=messages[-1]["content"],
                llm_kwargs=llm_kwargs,
                history=messages[:-1],
                sys_prompt=AGENT_SYSTEM_PROMPT,
                observe_window=[],
                console_slience=True
            )
        except Exception as e:
            return f"LLM 调用失败: {e}", step_log

        if not response:
            return "未收到模型回复", step_log

        tool_name, params = _parse_tool_call(response)

        if tool_name:
            result = _execute_tool(tool_name, params)
            step_log.append(f"🔧 {tool_name}: {result[:300]}")
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"工具结果:\n{result}\n\n继续下一步，或回复总结。"})
        else:
            return response, step_log

    return "已完成（达到最大步数）", step_log


def AI代码助手(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """
    AI Code Agent - modify code and add features through conversation.
    Type natural language to add features, change code, fix bugs.
    """
    if not txt or not txt.strip():
        chatbot.append(["AI代码助手", """## 🛠️ AI 代码助手

直接对话就能改代码、加功能：

**配置类：**
- `把默认模型改成 deepseek-v4-flash`
- `关闭代理` / `开启代理`
- `修改端口为 8080`

**功能类：**
- `加一个深色模式切换按钮`
- `添加清空对话历史的快捷按钮`
- `创建 Markdown 预览功能`

**修改类：**
- `把提交按钮文字改成发送`
- `修改页面上方的标题`

每次操作自动 git commit，方便回滚。
"""])
        yield from update_ui(chatbot=chatbot, history=history)
        return

    chatbot.append([txt, "🤔 正在执行..."])
    yield from update_ui(chatbot=chatbot, history=history)

    try:
        result, steps = _run_agent_loop(txt, llm_kwargs)

        final = result or "操作完成！"
        if steps:
            final = "\n".join(steps) + "\n\n---\n\n" + final

        chatbot.append([None, final])
        yield from update_ui(chatbot=chatbot, history=history)

    except Exception as e:
        report_exception(chatbot, history, str(e), traceback.format_exc())
