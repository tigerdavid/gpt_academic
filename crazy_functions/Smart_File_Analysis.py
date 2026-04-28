"""
Smart File Analysis - Auto-detect file type and apply best analysis plugin.
Drag-drop a file and click "智能分析" — no need to pick the right plugin manually.
"""

import os
import glob as glob_mod
from toolbox import update_ui, report_exception, get_log_folder, get_conf
from loguru import logger


FILE_TYPE_MAP = {
    ('.pdf',): '解析PDF',
    ('.docx', '.doc', '.odt'): '解析Word',
    ('.pptx', '.ppt'): '解析PPT',
    ('.xlsx', '.xls', '.csv'): '解析Excel',
    ('.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.c', '.h', '.rb', '.php', '.sh'): '代码审阅',
    ('.md', '.txt', '.rst', '.tex'): '总结文章',
    ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'): '图片解读',
    ('.mp3', '.wav', '.ogg', '.flac', '.m4a'): '音频转写',
    ('.mp4', '.avi', '.mov', '.mkv', '.webm'): '视频总结',
    ('.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'): '代码审阅',
    ('.zip', '.tar', '.gz', '.7z', '.rar'): '压缩包解包',
}


def 智能分析文件(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """
    Smart file analysis: detect file types in upload folder and auto-select the best plugin.
    
    Usage: upload file(s) via drag-drop, then click "智能分析" button.
    """
    try:
        from request_llms.bridge_all import model_info
        import importlib
        
        # Get the most recent upload folder
        user_name = llm_kwargs.get('username', 'default')
        if hasattr(llm_kwargs, 'get'):
            pass
        
        # Find files in private_upload
        import glob
        private_upload = 'private_upload'
        if not os.path.exists(private_upload):
            chatbot.append(["智能分析", "📭 请先拖拽/上传文件到输入区上方的上传区域。"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        # Walk all files in private_upload, sorted by mtime (newest first)
        all_files = []
        for root, dirs, files in os.walk(private_upload):
            for f in files:
                fp = os.path.join(root, f)
                all_files.append((fp, os.path.getmtime(fp)))
        
        if not all_files:
            chatbot.append(["智能分析", "📭 请先拖拽/上传文件到输入区上方的上传区域。"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        # Sort by mtime, newest first
        all_files.sort(key=lambda x: x[1], reverse=True)
        
        # Detect types for recent files (last 5 min)
        import time
        current_time = time.time()
        recent = [f[0] for f in all_files if current_time - f[1] < 300]  # 5 min
        if not recent:
            recent = [all_files[0][0]]  # at least one file
        
        # Detect file types
        ext = os.path.splitext(recent[0])[1].lower()
        
        detected_plugin = None
        for extensions, plugin_name in FILE_TYPE_MAP.items():
            if ext in extensions:
                detected_plugin = plugin_name
                break
        
        # Show file info
        files_str = "\n".join([f"📄 `{os.path.basename(f)}`" for f in recent[:5]])
        if len(recent) > 5:
            files_str += f"\n... 共 {len(recent)} 个文件"
        
        if detected_plugin:
            # Try to execute the detected plugin
            info = f"## 🔍 智能分析\n\n检测到文件：\n{files_str}\n\n类型：**{detected_plugin}** → 自动执行分析..."
            
            chatbot.append([f"智能分析上传文件", info])
            yield from update_ui(chatbot=chatbot, history=history)
            
            # Call the matching plugin via bridge
            try:
                from crazy_functional import get_crazy_functions
                plugins = get_crazy_functions()
                
                if detected_plugin in plugins and hasattr(plugins[detected_plugin], 'get') and \
                   plugins[detected_plugin].get("Function"):
                    plugin_fn = plugins[detected_plugin]["Function"]
                    
                    # Set the file path as input text
                    # Pass the first file path as input
                    file_path = recent[0]
                    yield from plugin_fn(file_path, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request)
                else:
                    # Fallback: use the text input with file path
                    chatbot.append([f"未找到插件 {detected_plugin}", f"请手动选择插件处理文件。\n文件路径：{recent[0]}"])
                    yield from update_ui(chatbot=chatbot, history=history)
            except Exception as e:
                report_exception(chatbot, history, str(e), f"执行插件 {detected_plugin} 失败")
                yield from update_ui(chatbot=chatbot, history=history)
        else:
            chatbot.append([f"智能分析", f"📄 文件：\n{files_str}\n\n⚠️ 未知文件类型（{ext}），请手动选择插件分析。"])
            yield from update_ui(chatbot=chatbot, history=history)

    except Exception as e:
        report_exception(chatbot, history, str(e), "智能分析失败")


def 文件列表(txt: str, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, user_request):
    """Show all uploaded files in private_upload."""
    try:
        private_upload = 'private_upload'
        if not os.path.exists(private_upload):
            chatbot.append(["文件列表", "📭 暂无上传文件。"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        all_files = []
        for root, dirs, files in os.walk(private_upload):
            for f in files:
                fp = os.path.join(root, f)
                size = os.path.getsize(fp)
                mtime = os.path.getmtime(fp)
                all_files.append((fp, size, mtime))

        if not all_files:
            chatbot.append(["文件列表", "📭 暂无上传文件。"])
            yield from update_ui(chatbot=chatbot, history=history)
            return

        all_files.sort(key=lambda x: x[2], reverse=True)
        
        lines = ["## 📁 上传文件列表\n"]
        for fp, size, mtime in all_files:
            size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/(1024*1024):.1f}MB"
            rel = os.path.relpath(fp, private_upload)
            lines.append(f"📄 `{rel}` — {size_str}")

        chatbot.append(["文件列表", "\n".join(lines)])
        yield from update_ui(chatbot=chatbot, history=history)

    except Exception as e:
        report_exception(chatbot, history, str(e), "文件列表错误")
