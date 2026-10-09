"""Seed saved definitions through local restore; never pretend fixture setup is editing."""
import json


def save_preset(app, slot=1, **changes):
    config = app.view()["config"]
    config["presets"][slot - 1].update(changes)
    if any(field in changes for field in ("pedal_sensitivity", "dynamic_assist")):
        config["presets"][slot - 1]["configured"] = True
    if "pedal_dip_compensation" in changes:
        config["presets"][slot - 1]["dip_included"] = True
    app.action("configuration_import_prepare", content=json.dumps(config))
    return app.action("configuration_import_commit")
