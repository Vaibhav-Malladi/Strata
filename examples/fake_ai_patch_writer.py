from pathlib import Path


def main() -> None:
    repo_root = Path.cwd()
    aidc_dir = repo_root / ".aidc"
    aidc_dir.mkdir(parents=True, exist_ok=True)

    patch_path = aidc_dir / "agent_patch.diff"
    patch_text = (
        "diff --git a/demo_patch_target.txt b/demo_patch_target.txt\n"
        "new file mode 100644\n"
        "index 0000000..e69de29\n"
        "--- /dev/null\n"
        "+++ b/demo_patch_target.txt\n"
        "@@ -0,0 +1 @@\n"
        "+This is a demo patch created by the fake command adapter.\n"
    )
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    print(f"Wrote demo patch to {patch_path}")


if __name__ == "__main__":
    main()
