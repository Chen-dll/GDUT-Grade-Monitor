# Contributing

Thanks for helping improve GDUT Grade Monitor.

## Development Setup

```powershell
python -m pip install -e ".[build]"
python -m unittest discover -s tests -v
```

## Safety Rules

- Keep the project read-only. Do not add endpoints that submit, save, delete, evaluate, update, or modify education-system data.
- Do not log passwords, cookies, tokens, full student IDs, or full grade snapshots.
- Store passwords only through `keyring`.
- Keep user data under `%USERPROFILE%\.gdut-grade-monitor`.

## Before Submitting Changes

```powershell
python -m unittest discover -s tests -v
python -m compileall gdut_grade_monitor tests packaging docs
```

For GUI-visible changes, also run the app locally and check the affected pages.

## Release Build

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipExeBuild
```

Release assets are generated under `dist\`.
