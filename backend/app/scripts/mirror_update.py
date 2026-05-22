# sample: app/scripts/example_script.py

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--params-file", required=True)
    args = parser.parse_args()

    with open(args.params_file) as f:
        params = json.load(f)

    print("Params:", params)

    # اگر موفق بود:
    return 0

    # اگر fail شد:
    # return 1


if __name__ == "__main__":
    sys.exit(main())