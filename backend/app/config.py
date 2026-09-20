import json
import os
from pathlib import Path
from cryptography.fernet import Fernet

DATA_DIR = Path(__file__).parent.parent / "data"
CONFIG_FILE = DATA_DIR / "config.enc.json"
KEY_FILE = DATA_DIR / ".key"

def _get_fernet():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        key = KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        os.chmod(KEY_FILE, 0o600)
    return Fernet(key)

def load_config():
    if not CONFIG_FILE.exists():
        return {"providers": {}, "active_provider": None, "exa_api_key": "", "defaults": {"depth": "standard", "max_sources": 20}}
    try:
        f = _get_fernet()
        data = f.decrypt(CONFIG_FILE.read_bytes())
        return json.loads(data)
    except Exception:
        return {"providers": {}, "active_provider": None, "exa_api_key": "", "defaults": {}}

def save_config(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = _get_fernet()
    CONFIG_FILE.write_bytes(f.encrypt(json.dumps(cfg).encode()))
    os.chmod(CONFIG_FILE, 0o600)
    return cfg

def get_provider_cfg(name=None):
    cfg = load_config()
    if name:
        return cfg.get("providers", {}).get(name)
    active = cfg.get("active_provider")
    if active:
        return cfg.get("providers", {}).get(active)
    # return first
    provs = cfg.get("providers", {})
    if provs:
        return list(provs.values())[0]
    return None
