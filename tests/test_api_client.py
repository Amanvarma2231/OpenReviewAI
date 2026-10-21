"""
Unit Tests for Ollama API Client
================================
Tests client connectivity, health checks, error raising, timeouts, and missing model handling
with mocked HTTP requests (no live Ollama server required).
"""

import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import ConnectionError, Timeout
from utils.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaError,
)


def test_health_check_online():
    client = OllamaClient(base_url="http://mock-server:11434")
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"version": "0.1.32"}
        mock_get.return_value = mock_resp

        health = client.check_health()
        assert health["status"] == "online"
        assert health["version"] == "0.1.32"


def test_health_check_offline():
    client = OllamaClient(base_url="http://mock-server:11434")
    with patch("requests.get", side_effect=ConnectionError("Connection refused")):
        health = client.check_health()
        assert health["status"] == "offline"
        assert health["version"] is None
        assert "Ensure Ollama is installed" in health["message"]


def test_health_check_timeout():
    client = OllamaClient(base_url="http://mock-server:11434")
    with patch("requests.get", side_effect=Timeout("Timed out")):
        health = client.check_health()
        assert health["status"] == "timeout"


def test_list_installed_models():
    client = OllamaClient(base_url="http://mock-server:11434")
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:3b"},
                {"name": "deepseek-coder:1.3b"}
            ]
        }
        mock_get.return_value = mock_resp

        models = client.list_installed_models()
        assert "qwen2.5-coder:3b" in models
        assert "deepseek-coder:1.3b" in models


def test_missing_model_raises_error():
    client = OllamaClient(base_url="http://mock-server:11434")
    with patch.object(client, "check_health", return_value={"status": "online"}), \
         patch.object(client, "list_installed_models", return_value=["qwen2.5-coder:1.5b"]):

        with pytest.raises(OllamaModelNotFoundError) as exc_info:
            client.chat(model="nonexistent-model:99b", messages=[{"role": "user", "content": "hi"}])
        assert "nonexistent-model:99b" in str(exc_info.value)
        assert "ollama pull" in str(exc_info.value)


def test_chat_timeout_raises_ollama_timeout_error():
    client = OllamaClient(base_url="http://mock-server:11434", timeout=5)
    with patch.object(client, "check_health", return_value={"status": "online"}), \
         patch.object(client, "list_installed_models", return_value=["qwen2.5-coder:3b"]), \
         patch("requests.post", side_effect=Timeout("Request timed out")):

        with pytest.raises(OllamaTimeoutError) as exc_info:
            client.chat(model="qwen2.5-coder:3b", messages=[{"role": "user", "content": "hi"}])
        assert "timed out after 5 seconds" in str(exc_info.value)


def test_mock_mode_execution():
    client = OllamaClient(mock_mode=True)
    health = client.check_health()
    assert health["status"] == "online"
    assert "mock" in health["version"].lower()

    res = client.chat(
        model="qwen2.5-coder:3b",
        messages=[{"role": "user", "content": "write a fibonacci function"}]
    )
    assert "def fibonacci" in res
