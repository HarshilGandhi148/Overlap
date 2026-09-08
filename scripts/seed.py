"""Run explicitly: python -m scripts.seed [eat|do|watch|play|all]."""
import argparse
from core.registry import load_categories
from core.services import AppServices, Settings


def seed_categories(services, selected="all"):
    ready, unavailable = load_categories()
    if selected != "all" and selected not in ready:
        raise RuntimeError(f"Category {selected!r} is not available.")
    reports = []
    for key, (spec, module) in ready.items():
        if selected == "all" or selected == key:
            report = module.seed(services)
            print(f"{spec.label}: {report.imported} imported, {report.failed} failed")
            reports.append(report)
            if report.errors:
                print("\n".join(report.errors))
    if unavailable:
        print("Not integrated: " + ", ".join(unavailable))
    if any(r.failed for r in reports):
        raise RuntimeError("Some imports failed. Fix the catalog before continuing.")
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", nargs="?", default="all")
    args = parser.parse_args()
    seed_categories(AppServices(Settings.from_env()), args.category)
