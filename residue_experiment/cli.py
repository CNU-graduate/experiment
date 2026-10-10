import argparse
import json
from pathlib import Path
from .runner import run
from .selection import CONDITIONS
from .providers import KEYS
from .evaluation import write_csv


def validate_config(config):
    if not config['years'] or any(type(y) is not int for y in config['years']) or len(set(config['years'])) != len(config['years']):
        raise ValueError('years must be nonempty and unique')
    if not config['seeds'] or any(type(s) is not int for s in config['seeds']) or len(set(config['seeds'])) != len(config['seeds']):
        raise ValueError('seeds must be unique integers')
    if not config['conditions'] or len(set(config['conditions'])) != len(config['conditions']) or not set(config['conditions']) <= set(CONDITIONS):
        raise ValueError('invalid conditions')
    if not config['models'] or not set(config['models']) <= set(KEYS):
        raise ValueError('invalid providers')
    for field in ('max_attempts', 'max_output_tokens', 'timeout_seconds'):
        if isinstance(config[field], bool) or not isinstance(config[field], (int, float)) or config[field] <= 0:
            raise ValueError(f'{field} must be positive')
    for field in ('max_attempts', 'max_output_tokens'):
        if type(config[field]) is not int:
            raise ValueError(f'{field} must be an integer')
    if config['retry_delay_seconds'] < 0:
        raise ValueError('retry_delay_seconds must be nonnegative')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live'], default='dry-run')
    parser.add_argument('--output', default='results/dry-run')
    parser.add_argument('--approve-paid-api', action='store_true', help='Use only after separate user approval')
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['data_dir'] = str((config_path.parent / config['data_dir']).resolve())
        validate_config(config)
        print(json.dumps(run(config, args.output, args.mode, args.approve_paid_api)))
    except (ValueError, KeyError, ImportError) as exc:
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        write_csv(output/'validation_errors.csv', [{'type': type(exc).__name__, 'reason': str(exc)}])
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
