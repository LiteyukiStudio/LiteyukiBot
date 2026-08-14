import hashlib
import json

from liteyukibot_webui import static_assets

assets = static_assets()
assert assets.is_dir()
manifest = assets.joinpath("assets.manifest.json")
assert manifest.is_file()
for item in json.loads(manifest.read_text(encoding="utf-8"))["files"]:
    asset = assets.joinpath(item["path"])
    assert asset.is_file()
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == item["sha256"]
