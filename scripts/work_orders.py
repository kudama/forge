"""Forge-side work-order preflight and result validation; never submits or applies."""
import argparse
import json
from pathlib import Path
import sys
from forge_controller.config import Settings
from forge_controller.work_orders import HandoffError, compile_task, load_json, validate_result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['compile','validate-result'])
    parser.add_argument('order', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--principal', required=True)
    args = parser.parse_args()
    try:
        settings = Settings.from_environment()
        order = load_json(args.order)
        if args.action=='compile':
            result = compile_task(order, settings, args.principal)
        else:
            if args.result is None or args.execution is None:
                raise HandoffError('result_and_execution_required')
            result = validate_result(order, load_json(args.result), load_json(args.execution), settings, args.principal)
        print(json.dumps(result))
    except (HandoffError, OSError, KeyError, ValueError):
        print('Work-order validation failed; check scope, source, limits and contract', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
