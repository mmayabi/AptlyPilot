# file: app/scripts/default_scripts.py

DEFAULT_SCRIPTS = [
    {
        "name": "mirror_update.py",
        "description": "Update a mirror",
        "params": {
            "mirror": {"required": True, "type": "str"},
            "url": {"required": True, "type": "str"}
        }
    },
    {
        "name": "snapshot_create.py",
        "description": "Create snapshot of repo",
        "params": {
            "snapshot": {"required": True, "type": "str"}
        }
    },
    {
        "name": "publish_switch.py",
        "description": "Switch published repo",
        "params": {}
    }
]