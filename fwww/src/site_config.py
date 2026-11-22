# ABOUTME: Reads the site settings from site.ini, then site_local.ini.
# ABOUTME: site_local.ini holds the keys and any settings of this machine; its values win.

import configparser, os

SITE_INI = 'site.ini'
LOCAL_INI = 'site_local.ini'
REQUIRED_KEYS = ('SESSION', 'OPENAI')

def read_config(directory):
    cfg = configparser.ConfigParser()
    if not cfg.read(os.path.join(directory, SITE_INI)):
        raise RuntimeError(f"Can't find config file {SITE_INI}")
    cfg.read(os.path.join(directory, LOCAL_INI))
    for key in REQUIRED_KEYS:
        if not cfg.get('KEYS', key, fallback=''):
            raise RuntimeError(f"No {key} in the [KEYS] section of {LOCAL_INI}")
    return cfg
