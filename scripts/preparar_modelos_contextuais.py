"""Download explícito de pesos públicos; nunca lê ou transmite currículos."""
import json
import argparse
from pathlib import Path
from huggingface_hub import snapshot_download


def main():
    root = Path('models/contextual')
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--include-transformers-test-model', action='store_true')
    args = parser.parse_args()
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    models = [('retrieval', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42')]
    if args.include_transformers_test_model:
        models.append(('evaluator', 'Qwen/Qwen2.5-1.5B-Instruct', '989aa7980e4cf806f80c7fef2b1adb7bc71aa306'))
    for key, repo, revision in models:
        target = root / key
        snapshot_download(repo, revision=revision, local_dir=target,
                          allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', '*.tiktoken'],
                          ignore_patterns=['onnx/*', 'openvino/*'])
        manifest[key] = dict(repository=repo, revision=revision, path=str(target.resolve()))
        (target / 'local-revision.json').write_text(json.dumps(manifest[key], indent=2), encoding='utf-8')
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Modelos locais preparados; manifesto em models/contextual/manifest.json')


if __name__ == '__main__':
    main()
