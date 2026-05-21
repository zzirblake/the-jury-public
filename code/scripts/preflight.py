"""Pre-flight API validation. Run before any expensive expansion.

Fires one minimal call per (configured_model x configured_temperature) cell.
Cost: pennies. Catches the class of bug where a model rejects a parameter
(e.g., Opus 4.7 rejecting `temperature`) or a temperature is out of range
(e.g., the legacy T=1.1 issue) BEFORE we pay for n=200 or n=1000 expansion.

Failure modes covered:
  - model ID rejected (NotFoundError / 404)
  - temperature out of range (BadRequestError "temperature is deprecated...")
  - permission denied / billing problem
  - any other API misconfiguration that fails closed at scale

Usage:
    python scripts/preflight.py [--config config.yaml]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import env_loader, variance  # noqa: E402

env_loader.load_anthropic_key()
import anthropic  # noqa: E402  (after env load)


def preflight(config_path: Path) -> int:
    """Return 0 if all checks pass, nonzero on any failure."""
    cfg = yaml.safe_load(config_path.read_text())
    default_model = cfg["expansion"]["default_model"]
    outlier_model = cfg["expansion"]["outlier_model"]
    temps = sorted(variance.TEMPERATURE_DISTRIBUTION.keys())

    client = anthropic.Anthropic()
    results = []

    # Test matrix: (default model x every configured temp) + (outlier model x every configured temp)
    matrix = [(default_model, t, "default") for t in temps] + \
             [(outlier_model, t, "outlier") for t in temps]

    print(f"=== API preflight ({len(matrix)} canary calls) ===")
    for model, temp, role in matrix:
        try:
            r = client.messages.create(
                model=model,
                max_tokens=8,
                temperature=float(temp),
                messages=[{"role": "user", "content": "ping"}],
            )
            results.append({"model": model, "temp": temp, "role": role, "ok": True})
            print(f"  [OK]   {role:8s} {model:25s} T={temp}")
        except anthropic.NotFoundError:
            results.append({"model": model, "temp": temp, "role": role, "ok": False,
                            "error": "model not found"})
            print(f"  [404]  {role:8s} {model:25s} T={temp}: model not found")
        except anthropic.BadRequestError as e:
            msg = str(e)
            short = msg.split("'message': '")[-1].split("'")[0][:120] if "'message':" in msg else msg[:120]
            results.append({"model": model, "temp": temp, "role": role, "ok": False,
                            "error": short})
            print(f"  [400]  {role:8s} {model:25s} T={temp}: {short}")
        except anthropic.PermissionDeniedError:
            results.append({"model": model, "temp": temp, "role": role, "ok": False,
                            "error": "permission denied"})
            print(f"  [403]  {role:8s} {model:25s} T={temp}: permission denied")
        except Exception as e:
            results.append({"model": model, "temp": temp, "role": role, "ok": False,
                            "error": f"{type(e).__name__}: {str(e)[:80]}"})
            print(f"  [ERR]  {role:8s} {model:25s} T={temp}: {type(e).__name__}: {str(e)[:80]}")

    failures = [r for r in results if not r["ok"]]
    print(f"\nPassed: {len(results) - len(failures)}/{len(results)}")
    if failures:
        print("\nFAILURES — fix before running paid expansion:")
        for f in failures:
            print(f"  {f['role']:8s} {f['model']:25s} T={f['temp']}: {f.get('error')}")
        return 1
    print("Preflight OK. Safe to run paid expansion.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    rc = preflight(REPO_ROOT / args.config)
    sys.exit(rc)


if __name__ == "__main__":
    main()
