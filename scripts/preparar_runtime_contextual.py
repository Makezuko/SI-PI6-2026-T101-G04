"""Baixa runtime oficial Windows e GGUF oficial Qwen; não lê currículos."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile
from huggingface_hub import HfApi, hf_hub_download


def main():
    root = Path('models/contextual')
    request = urllib.request.Request('https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b12477',
                                     headers={'User-Agent': 'TalentMatch-local-setup'})
    release = json.load(urllib.request.urlopen(request, timeout=60))
    asset = next(a for a in release['assets']
                 if 'win-cpu-x64' in a['name'] and a['name'].endswith('.zip'))
    blob = urllib.request.urlopen(asset['browser_download_url'], timeout=180).read()
    digest = hashlib.sha256(blob).hexdigest()
    if asset.get('digest') and asset['digest'] != 'sha256:' + digest:
        raise ValueError('Hash do runtime divergente')
    runtime = (root / 'llama-cpp').resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for item in archive.infolist():
            if not (runtime / item.filename).resolve().is_relative_to(runtime):
                raise ValueError('Caminho inválido no arquivo do runtime')
        archive.extractall(runtime)
    repo = 'unsloth/Qwen3-4B-Instruct-2507-GGUF'
    info = HfApi().model_info(repo, revision='a06e946bb6b655725eafa393f4a9745d460374c9')
    filename = next(f.rfilename for f in info.siblings if f.rfilename.lower().endswith('q4_k_m.gguf'))
    path = hf_hub_download(repo, filename, revision=info.sha, local_dir=root / 'gguf')
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('gguf', {}).get('repository') == 'Qwen/Qwen2.5-1.5B-Instruct-GGUF':
        manifest['rejected_1_5b'] = manifest['gguf']
    manifest['gguf'] = dict(repository=repo, revision=info.sha, path=str(Path(path).resolve()),
                            runtime=str(next(runtime.rglob('llama-server.exe'))),
                            runtime_asset=asset['name'], runtime_sha256=digest)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Runtime e GGUF locais preparados.')


if __name__ == '__main__':
    main()
