"""Only this registry needs changing when a new category is added."""
from importlib import import_module
import logging
from core.contracts import CategorySpec

CATEGORY_MODULES = {
    "eat": "categories.eat", "do": "categories.do", "watch": "categories.watch",
    "play": "categories.play", "anything": "categories.anything",
}


def load_categories():
    ready, unavailable = {}, {}
    for category_id, path in CATEGORY_MODULES.items():
        try:
            module = import_module(path)
            spec = module.get_spec()
            if not isinstance(spec, CategorySpec) or spec.id != category_id:
                raise ValueError("get_spec must return CategorySpec with the registered ID")
            if not callable(module.search) or not callable(module.seed):
                raise ValueError("search and seed must be callable")
            ready[category_id] = (spec, module)
        except Exception:
            logging.exception("Could not load category %s", category_id)
            unavailable[category_id] = "Category not ready. Check its module and shared contract."
    return ready, unavailable
