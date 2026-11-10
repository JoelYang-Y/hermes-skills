#!/usr/bin/env python3
"""
verify_fallback.py — End-to-end verification that a Hermes fallback provider is reachable.

Use this after adding a `fallback_providers` entry to ~/.hermes/config.yaml via the
bypass-config-guard recipe (see hermes-operations SKILL.md "Bypassing the Config Guard").

Steps performed:
  1. Load ~/.hermes/.env (which holds the masked API keys) into os.environ.
  2. Read fallback_providers from the live config via get_fallback_chain().
  3. For each entry: resolve the provider client, then send a tiny ping using the
     correct SDK (Anthropic SDK for minimax/minimax-cn; OpenAI SDK for everything else).
  4. Print PASS/FAIL per entry with the resolved base_url so misconfiguration is obvious.

Usage:
    ~/.hermes/hermes-agent/venv/bin/python3 verify_fallback.py
    ~/.hermes/hermes-agent/venv/bin/python3 verify_fallback.py --provider minimax-cn
    ~/.hermes/hermes-agent/venv/bin/python3 verify_fallback.py --all   # ping every entry

Exit code 0 = all reachable, 1 = at least one failed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
HERMES_AGENT = HERMES_HOME / "hermes-agent"
ENV_FILE = HERMES_HOME / ".env"


def _load_env() -> None:
    """Source ~/.hermes/.env into os.environ so the keys are visible to the SDKs."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        # Do NOT overwrite real keys already in env (they take precedence over masked values)
        if k not in os.environ:
            os.environ[k] = v


_ANTHROPIC_COMPAT_PROVIDERS = {"minimax", "minimax-cn", "minimax-oauth"}


def _ping_anthropic(provider: str, model: str, base_url: str) -> str:
    """Anthropic-SDK ping for minimax family. Requires anthropic package."""
    from anthropic import Anthropic

    key_env = "MINIMAX_API_KEY" if provider in {"minimax", "minimax-oauth"} else "MINIMAX_CN_API_KEY"
    api_key = os.environ.get(key_env, "")
    if not api_key:
        return f"FAIL: {key_env} not set in env"
    client = Anthropic(base_url=base_url, auth_token=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return f"PASS (reply: {text!r})" if "pong" in text.lower() else f"WEAK: {text!r}"


def _ping_openai(provider: str, model: str, base_url: str) -> str:
    """OpenAI-SDK ping for everything else."""
    from openai import OpenAI

    # Reuse the same env-var naming convention the rest of Hermes uses
    api_key = os.environ.get(f"{provider.upper().replace('-', '_')}_API_KEY", "")
    if not api_key:
        return f"FAIL: {provider.upper().replace('-', '_')}_API_KEY not set in env"
    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=20,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
    )
    text = resp.choices[0].message.content or ""
    return f"PASS (reply: {text!r})" if "pong" in text.lower() else f"WEAK: {text!r}"


def _resolve_base_url(provider: str, model: str) -> tuple[str, str]:
    """Use Hermes's own resolve_provider_client to learn the right base_url."""
    sys.path.insert(0, str(HERMES_AGENT))
    from agent.auxiliary_client import resolve_provider_client

    client, _ = resolve_provider_client(provider, model=model, raw_codex=True)
    if client is None:
        return "", "FAIL: resolve_provider_client returned None"
    base_url = (
        getattr(client, "base_url", None)
        or (getattr(client, "_client", None) and getattr(client._client, "base_url", None))
        or ""
    )
    return str(base_url), ""


def verify(provider_filter: str | None, do_all: bool) -> int:
    _load_env()

    sys.path.insert(0, str(HERMES_AGENT))
    from hermes_cli.config import load_config
    from hermes_cli.fallback_config import get_fallback_chain

    cfg = load_config()
    chain = get_fallback_chain(cfg)
    if not chain:
        print("No fallback_providers configured. Add one with `hermes fallback add` first.")
        return 1

    failures = 0
    for entry in chain:
        provider = entry.get("provider", "?")
        model = entry.get("model", "?")
        if provider_filter and provider != provider_filter:
            continue
        if not do_all and provider_filter is None and provider not in _ANTHROPIC_COMPAT_PROVIDERS:
            continue  # by default, only ping the minimax family (the common new entry)

        print(f"--- {provider} / {model} ---")
        base_url, err = _resolve_base_url(provider, model)
        if err:
            print(err)
            failures += 1
            continue
        print(f"  base_url: {base_url}")

        if provider in _ANTHROPIC_COMPAT_PROVIDERS:
            result = _ping_anthropic(provider, model, base_url)
        else:
            result = _ping_openai(provider, model, base_url)
        print(f"  {result}")
        if result.startswith("FAIL"):
            failures += 1

    print()
    if failures:
        print(f"{failures} failure(s) — fallback chain would NOT activate cleanly.")
        return 1
    print("All checked entries reachable. Fallback chain is verified live.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", help="Ping only this provider (e.g. minimax-cn)")
    p.add_argument("--all", action="store_true", help="Ping every entry, not just minimax family")
    args = p.parse_args()
    return verify(args.provider, args.all)


if __name__ == "__main__":
    raise SystemExit(main())