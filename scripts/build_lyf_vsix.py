"""Sync the shared LYF grammar and build a deterministic VSIX artifact."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAMMAR = ROOT / "tools" / "lyf" / "lyf.tmLanguage.json"
LANGUAGE_CONFIGURATION = ROOT / "tools" / "lyf" / "language-configuration.json"
EXTENSION = ROOT / "tools" / "vscode-lyf"


def sync_grammar() -> None:
    grammar = json.loads(GRAMMAR.read_text(encoding="utf-8"))
    if not isinstance(grammar, dict) or grammar.get("scopeName") != "source.lyf":
        raise ValueError("shared LYF grammar has an invalid TextMate scope")
    EXTENSION.joinpath("syntaxes").mkdir(parents=True, exist_ok=True)
    EXTENSION.joinpath("syntaxes", GRAMMAR.name).write_bytes(GRAMMAR.read_bytes())
    EXTENSION.joinpath(LANGUAGE_CONFIGURATION.name).write_bytes(LANGUAGE_CONFIGURATION.read_bytes())


def _manifest() -> bytes:
    return (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">\n'
        b'  <Metadata Include="LiteyukiStudio.LiteyukiLyf">\n'
        b'    <Identity Id="LiteyukiStudio.LiteyukiLyf" Version="0.8.0" '
        b'Language="en-US" Publisher="LiteyukiStudio" />\n'
        b'    <DisplayName>Liteyuki Function Language</DisplayName>\n'
        b'    <Description xml:space="preserve">Read-only LYF syntax highlighting.</Description>\n'
        b'    <Tags>lyf;liteyuki</Tags>\n'
        b'  </Metadata>\n'
        b'  <InstallationTarget Id="Microsoft.VisualStudio.Code" Version="[1.90.0,2.0.0)" />\n'
        b'  <Dependencies />\n'
        b'  <Assets>\n'
        b'    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" />\n'
        b'  </Assets>\n'
        b'</PackageManifest>\n'
    )


def build(output: Path) -> Path:
    sync_grammar()
    package = json.loads(EXTENSION.joinpath("package.json").read_text(encoding="utf-8"))
    package["version"] = "0.8.0"
    content_types = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        b'  <Default Extension="json" ContentType="application/json" />\n'
        b'  <Default Extension="md" ContentType="text/markdown" />\n'
        b'  <Default Extension="xml" ContentType="application/xml" />\n'
        b'  <Default Extension="lyf" ContentType="text/plain" />\n'
        b'</Types>\n'
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = {
            "[Content_Types].xml": content_types,
            "extension.vsixmanifest": _manifest(),
            "extension/package.json": json.dumps(package, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")
            + b"\n",
            "extension/language-configuration.json": LANGUAGE_CONFIGURATION.read_bytes(),
            "extension/syntaxes/lyf.tmLanguage.json": GRAMMAR.read_bytes(),
            "extension/README.md": EXTENSION.joinpath("README.md").read_bytes(),
            "extension/LICENSE": EXTENSION.joinpath("LICENSE").read_bytes(),
        }
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "liteyuki-lyf-0.8.0.vsix")
    args = parser.parse_args()
    print(build(args.out.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
