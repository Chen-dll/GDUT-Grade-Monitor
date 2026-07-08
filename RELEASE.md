# Release Checklist

Use this when publishing the project for other users.

1. Run tests:

   ```powershell
   python -m unittest discover -s tests -v
   python -m compileall gdut_grade_monitor tests
   python -m gdut_grade_monitor doctor
   ```

2. Verify setup on a clean Windows account or virtual machine:

   ```powershell
   git clone <repo-url>
   cd <repo-folder>
   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
   ```

   In the GUI, click `一键配置本机`, complete login, then confirm grades and autostart status.

3. Confirm no secrets are committed:

   - No `cookies.json`
   - No `config.json`
   - No `state.json`
   - No password or student account in docs or logs

4. Build release artifacts:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
   powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipExeBuild
   .\dist\GDUTGradeMonitor.exe
   ```

   `build_installer.ps1` requires Inno Setup. It produces `dist\GDUTGradeMonitor-Setup.exe`.

5. In the GUI, verify:

   - Environment check tab renders
   - Qt GUI opens by default
   - `python -m gdut_grade_monitor legacy-gui` still opens the Tkinter fallback
   - Top guidance card shows the next action
   - One-click setup works from a fresh data directory
   - Immediate check works
   - Autostart install points to the exe when running from packaged build
   - Password with Chinese/full-width input is rejected with a friendly message
   - About dialog shows version, author, and read-only boundary
   - Diagnostics export creates a zip without password, Cookie, full student id, or full grade details

6. In the installer, verify on a clean Windows account or VM:

   - Welcome/introduction page shows author and read-only notice
   - Install path defaults to the current user's LocalAppData
   - Desktop shortcut task is optional
   - Start Menu shortcut and uninstall entry are created
   - Finish page can launch the app
   - App still asks users to configure credentials inside the GUI, not the installer
