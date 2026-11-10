"""Tests for the model backends."""

import json

import pytest

from governed_agent.models import CloudModel, OllamaModel, ScriptedModel


def test_scripted_model_plays_script_then_stops():
    model = ScriptedModel(script=['{"tool": "list_dir", "args": {"path": "."}}'], seed=0)
    first = model.complete([{"role": "user", "content": "go"}])
    assert json.loads(first.text)["tool"] == "list_dir"
    second = model.complete([{"role": "user", "content": "go"}])
    assert json.loads(second.text)["done"] is True


def test_scripted_model_empty_script_is_done():
    model = ScriptedModel(script=[], seed=0)
    assert json.loads(model.complete([]).text)["done"] is True


def test_scripted_model_is_deterministic():
    script = ['{"tool": "read_file", "args": {"path": "a.py"}}']
    a = ScriptedModel(script=script, seed=0)
    b = ScriptedModel(script=script, seed=0)
    assert a.complete([]).text == b.complete([]).text
    assert a.complete([]).text == b.complete([]).text


def test_scripted_model_variants_by_seed():
    variants = {
        0: ['{"done": true, "result": "seed zero"}'],
        1: ['{"done": true, "result": "seed one"}'],
    }
    a = ScriptedModel(variants=variants, seed=0)
    b = ScriptedModel(variants=variants, seed=1)
    assert json.loads(a.complete([]).text)["result"] == "seed zero"
    assert json.loads(b.complete([]).text)["result"] == "seed one"


def test_ollama_model_fails_clearly_when_no_server():
    model = OllamaModel(model="llama3.1:8b", host="http://127.0.0.1:1")
    with pytest.raises(RuntimeError, match="Ollama is not reachable"):
        model.complete([{"role": "user", "content": "hi"}])


def test_cloud_model_requires_api_key_at_call_time(monkeypatch):
    monkeypatch.delenv("GOVERNED_AGENT_API_KEY", raising=False)
    model = CloudModel()
    with pytest.raises(RuntimeError, match="No cloud API key"):
        model.complete([{"role": "user", "content": "hi"}])
    assert model.cost_usd(1000, 1000) is None  # no price configured: unknown, not invented
