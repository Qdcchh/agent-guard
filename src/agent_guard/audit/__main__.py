"""Run the independent audit HTTPS service from explicit private configuration."""

import argparse
import sys
from pathlib import Path

from agent_guard.audit.config import AuditConfig
from agent_guard.audit.server import serve


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        serve(AuditConfig.load(args.config))
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("audit startup rejected configuration, domain or external pin", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
