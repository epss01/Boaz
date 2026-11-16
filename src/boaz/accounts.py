"""Local remembered account settings and packaged recognition assets."""
import json
from pathlib import Path
import shutil
from .config import Settings, atomic_json, load_settings, preset_path, save_settings


def install_assets(local: Path):
    source = Path(__file__).parent/'assets'/'recognition'
    if source.is_dir():
        for file in source.rglob('*'):
            if file.is_file():
                target = local/file.relative_to(source)
                if not target.exists():
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(file,target)


def initial_settings(local: Path):
    remembered = local/'last-account.json'
    if remembered.exists():
        name = json.loads(remembered.read_text(encoding='utf-8'))['account']
        return load_settings(preset_path(local/'accounts',name))
    existing = local/'presets'/'my-farm.json'
    if existing.exists():
        return load_settings(existing)
    cfg = Settings()
    cfg.live.profile = 'boaz-default'
    if (local/'tesseract'/'tesseract.exe').is_file():
        cfg.live.tesseract_path = str((local/'tesseract'/'tesseract.exe').resolve())
    for path in (Path(r'C:\Program Files\BlueStacks_polar\HD-Adb.exe'),Path(r'C:\Program Files\BlueStacks_nxt\HD-Adb.exe')):
        if path.is_file():
            cfg.device.adb_path = str(path)
            break
    return cfg


def remember_account(local: Path, cfg: Settings):
    name = cfg.walls.player_tag.removeprefix('#')
    if not name:
        raise ValueError('Identify and confirm an account first')
    save_settings(preset_path(local/'accounts',name),cfg)
    atomic_json(local/'last-account.json',{'account':name})
