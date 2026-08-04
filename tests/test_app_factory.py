"""Regression tests for centralized application assembly."""

from collections import Counter

from src.app import create_app
from src.shared.config.settings import Settings


_HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "trace",
}


def _openapi_operations(app):
    schema = app.openapi()
    return [
        (method, path, operation.get("operationId"))
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in _HTTP_METHODS
    ]


def test_factory_uses_lifespan_without_deprecated_startup_handlers():
    app = create_app(Settings())

    assert app.router.on_startup == []
    assert app.router.lifespan_context is not None


def test_factory_registers_unique_openapi_operations():
    app = create_app(Settings())
    operations = _openapi_operations(app)

    method_paths = [(method, path) for method, path, _ in operations]
    operation_ids = [
        operation_id
        for _, _, operation_id in operations
        if operation_id
    ]

    duplicate_method_paths = {
        operation: count
        for operation, count in Counter(method_paths).items()
        if count > 1
    }
    duplicate_operation_ids = {
        operation_id: count
        for operation_id, count in Counter(operation_ids).items()
        if count > 1
    }

    assert duplicate_method_paths == {}
    assert duplicate_operation_ids == {}


def test_resource_hierarchy_routes_are_owned_by_domain_routers():
    app = create_app(Settings())
    paths = set(app.openapi()["paths"])

    assert "/clients/{client_id}/projects" in paths
    assert "/projects/{project_id}/history" in paths
