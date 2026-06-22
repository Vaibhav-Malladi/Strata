from status import analyze_status, format_status_report
from cli_ui import print_title


def show_status(root: str = ".") -> None:
    status = analyze_status(root)
    report = format_status_report(status)

    print_title("Strata status")
    print(report)