from status import analyze_status, format_status_report
from ui import build_banner, build_kv_table, build_section, format_path


def show_status(root: str = ".") -> None:
    status = analyze_status(root)
    report = format_status_report(status)

    print(build_banner())
    print()
    print(build_section("Strata status"))
    print(
        build_kv_table(
            [
                ("Root", format_path(status.get("root", root))),
                ("State", status.get("state", "unknown")),
                ("Missing", len(status.get("missing_files", []))),
                ("Stale", len(status.get("stale_files", []))),
            ]
        )
    )
    print()
    print(report)
