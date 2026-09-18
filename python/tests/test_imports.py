def test_public_exports_are_importable():
    import confidentai
    from confidentai import ConfidentAI, ConfidentApiError

    assert confidentai.__version__
    assert ConfidentAI is not None
    assert issubclass(ConfidentApiError, Exception)


def test_api_primitives_exported():
    from confidentai import (
        Api,
        ApiResponse,
        ConfidentApiError,
        Endpoints,
        HttpMethods,
    )

    assert Api is not None
    assert ApiResponse is not None
    assert issubclass(ConfidentApiError, Exception)
    assert Endpoints is not None
    assert HttpMethods is not None


def test_generated_types_live_with_their_resource():
    from confidentai.organization.types import Organization
    from confidentai.projects.types import Project

    assert Organization is not None
    assert Project is not None


def test_every_module_in_the_package_imports():
    import importlib
    from pathlib import Path

    import confidentai

    root = Path(confidentai.__file__).parent
    modules = sorted(
        ".".join(("confidentai",) + path.relative_to(root).parts)[
            : -len(".py")
        ].removesuffix(".__init__")
        for path in root.rglob("*.py")
    )
    assert len(modules) > 100, f"only found {len(modules)} modules to import"

    failures = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - reported, not handled
            failures.append(f"{name}: {error}")

    assert not failures, "these modules could not be imported:\n" + "\n".join(
        failures
    )
