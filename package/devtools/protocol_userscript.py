"""
UserScript loader - parses Tampermonkey-style metadata and builds CDP injection commands.
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class UserScript:
    name: str
    description: str
    match: str
    run_at: str
    inject_into: str
    source: str
    file_path: str

    def __repr__(self):
        return f"UserScript(name={self.name!r}, run_at={self.run_at!r}, file={os.path.basename(self.file_path)!r})"


def parse_metadata(source: str) -> dict:
    metadata = {}
    in_block = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped == "// ==UserScript==":
            in_block = True
            continue
        if stripped == "// ==/UserScript==":
            break
        if in_block and stripped.startswith("// @"):
            m = re.match(r"^//\s*@(\S+)\s*(.*?)\s*$", stripped)
            if m:
                metadata[m.group(1)] = m.group(2)
    return metadata


def load_userscripts(scripts_dir: str) -> List[UserScript]:
    scripts = []
    scripts_path = Path(scripts_dir)
    if not scripts_path.exists():
        return scripts
    for js_file in sorted(scripts_path.glob("*.js")):
        script = _load_single_file(js_file)
        if script:
            scripts.append(script)
    return scripts


def load_userscripts_by_files(file_paths: List[str]) -> List[UserScript]:
    scripts = []
    for fp in file_paths:
        p = Path(fp)
        if not p.exists():
            continue
        script = _load_single_file(p)
        if script:
            scripts.append(script)
    return scripts


def _load_single_file(js_file: Path) -> UserScript | None:
    try:
        source = js_file.read_text(encoding="utf-8")
    except Exception:
        return None
    meta = parse_metadata(source)
    return UserScript(
        name=meta.get("name", js_file.stem),
        description=meta.get("description", ""),
        match=meta.get("match", "*"),
        run_at=meta.get("run-at", "document-start"),
        inject_into=meta.get("inject-into", "page"),
        source=source,
        file_path=str(js_file),
    )


def _indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def build_injection_wrapper(script: UserScript) -> str:
    safe_name = script.name.replace("\\", "\\\\").replace("'", "\\'")
    return f"""(function() {{
  'use strict';
  try {{
{_indent(script.source, 4)}
  }} catch(__e__) {{
    console.error('[UserScript] Error in "{safe_name}":', __e__);
  }}
}})();"""


def build_cdp_add_script_command(script: UserScript, cmd_id: int) -> str:
    wrapped = build_injection_wrapper(script)
    return json.dumps({
        "id": cmd_id,
        "method": "Page.addScriptToEvaluateOnNewDocument",
        "params": {"source": wrapped},
    })


def build_cdp_enable_page_command(cmd_id: int) -> str:
    return json.dumps({"id": cmd_id, "method": "Page.enable", "params": {}})
