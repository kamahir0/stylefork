"""Verified migration into the compact project layout; source data is never deleted."""
from __future__ import annotations
import shutil
from collections import defaultdict
from pathlib import Path
from .storage import read_json, atomic_write_json, sha256_file, now_iso

def resolve_aliases(value, root):
    root = Path(root)
    alias_path = root / '.stylefork/path_aliases.json'
    if not alias_path.exists(): alias_path = root / '.research/path_aliases.json'
    aliases = read_json(alias_path) if alias_path.exists() else {}
    def visit(item):
        if isinstance(item, str):
            seen = set()
            while item in aliases and item not in seen:
                seen.add(item); item = aliases[item]
            return item
        if isinstance(item, list): return [visit(v) for v in item]
        if isinstance(item, dict): return {visit(k): visit(v) for k, v in item.items()}
        return item
    return visit(value)

def image_extension(path):
    with path.open('rb') as stream: header = stream.read(12)
    if header.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if header.startswith(b'\xff\xd8\xff'): return '.jpg'
    if header.startswith(b'RIFF') and header[8:12] == b'WEBP': return '.webp'
    return None

def migrate(root, *, apply=False):
    root = Path(root).resolve()
    if (root / '.stylefork/config.json').exists() and not any((root / name).exists() for name in ['.stylekit','.research','.evidence-harness','ai']):
        return {'already_modern': True, 'source_data_deleted': False}
    if (root / '.stylefork/migration/report.json').exists():
        return {**read_json(root / '.stylefork/migration/report.json'), 'already_migrated': True}
    sources = []
    for name in ['ai', '.stylekit', '.research', '.evidence-harness', 'ComfyUI/output', 'output']:
        sources.extend(p for p in (root / name).rglob('*') if p.is_file())
    groups = defaultdict(list); image_hashes = {}
    for path in sources:
        extension = image_extension(path)
        if extension:
            hashed = sha256_file(path); groups[hashed].append((path, extension)); image_hashes[path] = hashed
    aliases = read_json(root / '.research/path_aliases.json') if (root / '.research/path_aliases.json').exists() else {}
    copies = {}; media = []
    for hashed, candidates in groups.items():
        ordered = sorted(candidates, key=lambda c: (0 if c[0].is_relative_to(root/'output') else 1 if c[0].is_relative_to(root/'ai/output') else 2 if c[0].is_relative_to(root/'ai/reference') else 3, str(c[0])))
        source, extension = ordered[0]
        if source.is_relative_to(root / 'output'): target = source
        elif source.is_relative_to(root / 'ai/output'): target = root / 'output' / source.relative_to(root / 'ai/output')
        elif source.is_relative_to(root / 'ai/reference'): target = root / '.stylefork/references' / source.relative_to(root / 'ai/reference')
        else: target = root / 'output/legacy_preserved' / (hashed[:20] + extension)
        copies[source] = target; relative = target.relative_to(root).as_posix()
        media.append({'path': relative, 'image_path': relative, 'sha256': hashed,
                      'experiment_id': 'asset-' + hashed[:20], 'output_index': 0, 'label': source.stem,
                      'batch_id': 'historical-assets', 'track_id': 'reference' if '/references/' in relative else 'historical-assets',
                      'created_at': '', 'hypothesis': 'Preserved image from the previous workspace'})
        for path, _ in candidates:
            aliases[path.relative_to(root).as_posix()] = relative
            aliases[str(path)] = str(target); aliases[path.as_posix()] = target.as_posix()
    style_sources = list((root / '.stylekit/styles').glob('*.json'))
    for path in style_sources:
        target = root / 'styles' / path.name; copies[path] = target
        aliases[path.relative_to(root).as_posix()] = target.relative_to(root).as_posix()
    metadata_count = 0
    for source in sources:
        if source in image_hashes or source in style_sources: continue
        relative = source.relative_to(root).as_posix()
        if source.suffix.lower() in {'.py', '.pyc', '.log', '.tmp'}: continue
        if relative in {'ai/output/CATALOG.md', 'ai/output/PRODUCTION_LOG.md', '.stylekit/config.json'}: continue
        if relative == '.research/state.json': target = root / '.stylefork/history/research.json'
        elif relative == '.evidence-harness/state.json': target = root / '.stylefork/history/evidence.json'
        elif relative.startswith('.research/reviews/'):
            target = root / '.stylefork/reviews' / source.relative_to(root / '.research/reviews')
        elif relative.startswith('.stylekit/'):
            target = root / '.stylefork' / source.relative_to(root / '.stylekit')
        else:
            hashed = sha256_file(source)
            extension = source.suffix if source.suffix.lower() in {'.json', '.jsonl', '.md', '.txt', '.yaml', '.yml'} else '.bin'
            target = root / '.stylefork/history/blobs' / (hashed + extension)
        copies[source] = target; aliases[relative] = target.relative_to(root).as_posix(); metadata_count += 1
    report = {'schema_version': 1, 'created_at': now_iso(), 'unique_images': len(groups),
              'source_image_copies': len(image_hashes), 'saved_styles': len(style_sources),
              'metadata_sources': metadata_count, 'source_data_deleted': False}
    for source, target in copies.items():
        if not target.resolve().is_relative_to(root): raise ValueError('Migration target escaped project')
        if target.exists() and sha256_file(target) != sha256_file(source): raise ValueError('Destination collision: ' + str(target))
    if not apply: return report
    for source, target in copies.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve() and not target.exists(): shutil.copy2(source, target)
        if sha256_file(source) != sha256_file(target): raise ValueError('Migration verification failed: ' + str(source))
    config = read_json(root / '.stylekit/config.json') if (root / '.stylekit/config.json').exists() else {}
    config.update(schema_version=2, kit_home=str(Path(__file__).resolve().parents[1]))
    atomic_write_json(root / '.stylefork/config.json', config)
    atomic_write_json(root / '.stylefork/path_aliases.json', aliases)
    atomic_write_json(root / '.stylefork/media.json', media)
    atomic_write_json(root / '.stylefork/migration/report.json', report)
    atomic_write_json(root / '.stylefork/migration/files.json', [
        {'source': p.relative_to(root).as_posix(), 'target': t.relative_to(root).as_posix(), 'sha256': sha256_file(t)} for p, t in copies.items()])
    from .workspace import Workspace
    Workspace(root).init()
    return report
