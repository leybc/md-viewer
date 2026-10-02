"""单实例 IPC 处理逻辑单测（不启动 GUI，mock 窗口对象）。"""

import json
from unittest.mock import MagicMock

import main


def test_handle_ipc_payload_opens_files():
    """带文件路径的请求：逐个通知前端加载并应答 OK。"""
    window = MagicMock()
    payload = json.dumps({"paths": [r"D:\docs\note.md"]}).encode("utf-8")
    reply = main._handle_ipc_payload(window, payload)
    assert reply == b"OK"
    js = window.evaluate_js.call_args[0][0]
    assert "loadFromPath" in js
    assert "note.md" in js


def test_handle_ipc_payload_empty_focuses_window():
    """边界：空路径列表（无参数双击 exe）只聚焦已有窗口，不分发加载。"""
    window = MagicMock()
    reply = main._handle_ipc_payload(window, json.dumps({"paths": []}).encode("utf-8"))
    assert reply == b"OK"
    window.show.assert_called_once()
    window.evaluate_js.assert_not_called()


def test_handle_ipc_payload_bad_json_replies_err():
    """边界：载荷不是合法 JSON 时应答 ERR 且不触发前端调用。"""
    window = MagicMock()
    reply = main._handle_ipc_payload(window, b"not a json")
    assert reply == b"ERR"
    window.evaluate_js.assert_not_called()


def test_handle_ipc_payload_filters_invalid_entries():
    """边界：非字符串与空白路径项被过滤，合法项仍分发。"""
    window = MagicMock()
    payload = json.dumps({"paths": ["", "   ", 123, r"D:\ok.md"]}).encode("utf-8")
    reply = main._handle_ipc_payload(window, payload)
    assert reply == b"OK"
    js = window.evaluate_js.call_args[0][0]
    assert "ok.md" in js
    assert window.evaluate_js.call_count == 1


def test_forward_returns_false_when_nobody_listens():
    """边界：无实例监听（连接失败）时返回 False，本进程按主实例启动。"""
    import socket as socket_module

    s = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))  # 占用一个空闲端口但不 listen
    free_port = s.getsockname()[1]
    s.close()
    # 用未监听的端口模拟"无人监听"：临时替换 IPC_PORT
    original = main.IPC_PORT
    main.IPC_PORT = free_port
    try:
        assert main._try_forward_to_running_instance([r"D:\x.md"]) is False
    finally:
        main.IPC_PORT = original
