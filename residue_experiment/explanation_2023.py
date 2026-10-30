"""Run the 2023 GPT P0 explanation variant once, without few-shot examples."""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from .cli import validate_config
from .explanation import EXPLANATION_SYSTEM
from .runner import run


def prepare(config):
    config = dict(config)
    if set(config['models']) != {'openai'}:
        raise ValueError('This experiment requires only the openai provider')
    model = config['models']['openai']
    if not isinstance(model, str) or not model.split('/')[-1].startswith('gpt-'):
        raise ValueError('This experiment requires an explicit GPT model')
    config.update(years=[2023], conditions=['E0'], seeds=[42], response_format='explanation')
    validate_config(config)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config.explanation-2023.gpt.json')
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live'], default='dry-run')
    parser.add_argument('--output', help='Reuse only to resume the same run')
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    path = Path(args.config).resolve()
    config = json.loads(path.read_text(encoding='utf-8'))
    load_dotenv(path.parent / '.env', override=False)
    config['models'] = {p: os.getenv(config.get('model_env', {}).get(p, '')) or m
                        for p, m in config['models'].items()}
    config['data_dir'] = str((path.parent / config['data_dir']).resolve())
    config = prepare(config)
    output = Path(args.output or f'results/p0-explanation/gpt/2023/{args.mode}')
    result = run(config, output, args.mode, args.approve_paid_api,
                 system_prompt=EXPLANATION_SYSTEM)
    print(json.dumps(dict(result, output=str(output.resolve()))))


if __name__ == '__main__':
    main()
