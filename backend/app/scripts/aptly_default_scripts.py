# file: app/scripts/default_scripts.py

DEFAULT_SCRIPTS = [
    {
        "name": "aptly.mirror.update",
        "description": "Update an Aptly mirror using the Aptly API",
        "params": {
            "run_async": {"required": False, "type": "bool"},
            "wait": {"required": False, "type": "bool"},
            "force_update": {"required": False, "type": "bool"},
            "skip_existing_packages": {"required": False, "type": "bool"},
            "poll_interval": {"required": False, "type": "int"},
            "max_wait_seconds": {"required": False, "type": "int"}
        }
    },
    {
        "name": "aptly.snapshot.create",
        "description": "Create an Aptly snapshot from the repository mirror",
        "params": {
            "fail_if_exists": {"required": False, "type": "bool"},
            "run_async": {"required": False, "type": "bool"},
            "wait": {"required": False, "type": "bool"},
            "poll_interval": {"required": False, "type": "int"},
            "max_wait_seconds": {"required": False, "type": "int"}
        }
    },
    {
        "name": "aptly.publish.switch",
        "description": "Publish a snapshot or switch an existing publication to it",
        "params": {
            "force_overwrite": {"required": False, "type": "bool"}
        }
    },
    {
        "name": "aptly.retention.cleanup",
        "description": "Delete old Aptly snapshots according to repository retention",
        "params": {
            "force": {"required": False, "type": "bool"}
        }
    },
    {
        "name": "aptly.inventory.sync",
        "description": "Refresh local Aptly inventory state from the Aptly API",
        "params": {}
    },
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


DEFAULT_JOB_TEMPLATES = [
    {
        "name": "aptly.repository.pipeline",
        "description": (
            "Update mirror, create snapshot, publish or switch it, "
            "clean old snapshots, and refresh Aptly inventory."
        ),
        "steps": [
            {
                "script_name": "aptly.mirror.update",
                "order": 10,
                "description": "Update the configured Aptly mirror",
            },
            {
                "script_name": "aptly.snapshot.create",
                "order": 20,
                "description": "Create a snapshot using repository snapshot config",
            },
            {
                "script_name": "aptly.publish.switch",
                "order": 30,
                "description": "Publish or switch to the latest configured snapshot",
            },
            {
                "script_name": "aptly.retention.cleanup",
                "order": 40,
                "description": "Delete old unpublished snapshots according to retention config",
            },
            {
                "script_name": "aptly.inventory.sync",
                "order": 50,
                "description": "Refresh local Aptly inventory state",
            },
        ],
    },
]
