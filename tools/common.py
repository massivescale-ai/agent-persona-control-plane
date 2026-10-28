"""Shared loaders for lint, compile, and check."""
import pathlib
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_yaml(path):
    # BaseLoader keeps every scalar as a string, so a date stays a date string.
    with open(path) as fh:
        return yaml.load(fh, Loader=yaml.BaseLoader)


def catalog():
    tools = load_yaml(ROOT / "catalog/tools.yaml")["tools"]
    classes = {k: int(v) for k, v in load_yaml(ROOT / "catalog/data-classes.yaml")["data_classes"].items()}
    platform = load_yaml(ROOT / "catalog/platform.yaml")
    return tools, classes, platform


def persona_files(args):
    if args:
        return [pathlib.Path(a) for a in args]
    return sorted((ROOT / "personas").glob("*.yaml"))


def derived_tier(persona, classes):
    return max(classes[c] for c in persona["data_classes"] if c in classes)
