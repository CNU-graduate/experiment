"""Download public EFSA article XML mirrors for source verification only."""
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = {2022: 'PMC13151657', 2023: 'PMC10466198', 2024: 'PMC11255603'}


def fetch(item):
    year, pmcid = item
    target = HERE / 'sources' / f'{year}.xml'
    if target.exists():
        return dict(year=year, pmcid=pmcid, cached=True, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    if year == 2022:
        query = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:10.2903/j.efsa.2022.7521&format=json'
        with urllib.request.urlopen(query, timeout=30) as response:
            metadata = json.load(response)
        (HERE / 'sources').mkdir(parents=True, exist_ok=True)
        (HERE / 'sources' / '2022_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        results = metadata.get('resultList', {}).get('result', [])
        matches = [r['pmcid'] for r in results if r.get('pmcid')]
        if matches:
            pmcid = matches[0]
    url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'
    with urllib.request.urlopen(url, timeout=40) as response:
        content = response.read()
    if b'<article' not in content:
        raise ValueError(f'{year}: not article XML')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return dict(year=year, pmcid=pmcid, url=url, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch, SOURCES.items()))
    (HERE / 'sources' / 'downloads.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    print(json.dumps(records, indent=2))
