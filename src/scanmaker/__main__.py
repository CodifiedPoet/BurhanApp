"""Allow running the package with ``python -m scanmaker``."""

from .app import ScanGeneratorApp


def main():
    app = ScanGeneratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
