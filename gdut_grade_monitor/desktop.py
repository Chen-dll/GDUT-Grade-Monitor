from __future__ import annotations

import sys


def main() -> None:
    from .cli import _configure_logging, _paths

    paths = _paths()
    if "--monitor" in sys.argv:
        from .cli import _make_monitor

        _configure_logging(paths)
        _make_monitor(paths).run_forever()
        return

    _configure_logging(paths)

    if "--legacy-gui" in sys.argv:
        from .gui import main as legacy_gui_main

        legacy_gui_main()
        return

    from .qt_gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
