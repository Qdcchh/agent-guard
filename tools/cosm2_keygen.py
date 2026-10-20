"""Generate local prototype COSM2 shares without printing private material."""

import argparse
import json

from agent_guard.cosign.shares import generate_shares


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--key-epoch", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(generate_shares(args.directory, key_epoch=args.key_epoch)))


if __name__ == "__main__":
    main()
