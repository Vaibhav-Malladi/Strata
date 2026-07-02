import re


FRONTEND_ROLES = (
    "page",
    "component",
    "template",
    "style",
    "hook",
    "service",
    "api_client",
    "route",
    "state_store",
    "form",
    "test",
    "config",
    "asset",
    "unknown",
)

_SCRIPT_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
_TEMPLATE_EXTENSIONS = {".html"}
_STYLE_EXTENSIONS = {".css", ".scss", ".sass", ".less"}
_ASSET_EXTENSIONS = {
    ".avif",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
}
_FRONTEND_EXTENSIONS = (
    _SCRIPT_EXTENSIONS | _TEMPLATE_EXTENSIONS | _STYLE_EXTENSIONS | _ASSET_EXTENSIONS
)

_TEST_PARTS = {"__tests__", "e2e", "spec", "specs", "test", "tests"}
_PAGE_FOLDERS = {"page", "pages", "screen", "screens", "view", "views"}
_COMPONENT_FOLDERS = {"component", "components"}
_HOOK_FOLDERS = {"hook", "hooks"}
_API_FOLDERS = {"api", "apis", "client", "clients"}
_STORE_FOLDERS = {"state", "store", "stores"}
_ROUTE_FOLDERS = {"route", "router", "routers", "routes", "routing"}
_FORM_FOLDERS = {"form", "forms"}
_ASSET_FOLDERS = {"asset", "assets", "image", "images", "public", "static"}


def infer_frontend_role_from_path(path: str) -> str:
    """Infer an approximate frontend role from path signals only."""

    parts, filename, stem, extension = _path_details(path)
    if not filename or extension not in _FRONTEND_EXTENSIONS:
        return "unknown"

    folders = {part.lower() for part in parts[:-1]}
    normalized_filename = filename.lower()
    normalized_stem = stem.lower()
    if _is_test_name(normalized_stem) or folders & _TEST_PARTS:
        return "test"
    if _is_config_name(normalized_filename, normalized_stem):
        return "config"
    if extension in _ASSET_EXTENSIONS or folders & _ASSET_FOLDERS:
        return "asset"

    # Angular conventions are intentionally recognized by suffix, without parsing.
    if ".component." in normalized_filename:
        if extension in _TEMPLATE_EXTENSIONS:
            return "template"
        if extension in _STYLE_EXTENSIONS:
            return "style"
        return "component"
    if any(
        marker in normalized_filename
        for marker in (".service.", ".guard.", ".resolver.")
    ):
        return "service"
    if ".routes." in normalized_filename or "routing.module." in normalized_filename:
        return "route"

    tokens = set(_name_tokens(stem))
    if folders & _PAGE_FOLDERS or "page" in tokens:
        return "page"
    if folders & _HOOK_FOLDERS or _looks_like_hook(stem):
        return "hook"
    if folders & _ROUTE_FOLDERS or tokens & {"route", "routes", "router", "routing"}:
        return "route"
    if folders & _API_FOLDERS or "api" in tokens or "client" in tokens:
        return "api_client"
    if folders & _STORE_FOLDERS or tokens & {"store", "reducer", "slice"}:
        return "state_store"
    if folders & _FORM_FOLDERS:
        return "form"
    if folders & _COMPONENT_FOLDERS or extension in {".jsx", ".tsx"}:
        return "component"
    if extension in _TEMPLATE_EXTENSIONS:
        return "template"
    if extension in _STYLE_EXTENSIONS:
        return "style"
    return "unknown"


def is_frontend_candidate(path: str) -> bool:
    """Return whether a path has a supported frontend-oriented extension."""

    _, filename, _, extension = _path_details(path)
    return bool(filename and extension in _FRONTEND_EXTENSIONS)


def _path_details(path: str) -> tuple[tuple[str, ...], str, str, str]:
    normalized = str(path).replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part and part != ".")
    filename = parts[-1] if parts else ""
    if "." not in filename:
        return parts, filename, filename, ""
    stem, extension = filename.rsplit(".", 1)
    return parts, filename, stem, f".{extension.lower()}"


def _is_test_name(stem: str) -> bool:
    return bool(re.search(r"(^test[._-]|[._-](test|spec)$)", stem))


def _is_config_name(filename: str, stem: str) -> bool:
    return (
        ".config." in filename
        or stem in {"angular", "babel", "eslint", "jest", "postcss", "tailwind", "vite"}
    )


def _looks_like_hook(stem: str) -> bool:
    normalized = stem.lower()
    return normalized.startswith("use") and not normalized.startswith("user")


def _name_tokens(value: str) -> tuple[str, ...]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return tuple(re.findall(r"[a-z0-9]+", separated.lower()))
