#!/usr/bin/env python3
"""Interlock Terminal Runner - the command-line interface to the recovery engine.

This is one of Interlock's two product interfaces (the other is the VS Code
extension). Both drive the SAME shared Python recovery engine through the SAME
orchestration layer (``interlock_bridge.py``); this module adds nothing but a
terminal-friendly presentation on top. Recovery logic is never duplicated here:

  - argument parsing reuses the bridge's own parser (identical flags);
  - every operation calls the bridge's own ``cmd_*`` handlers;
  - exit codes are the bridge's exit codes.

Product operations and their engine commands:

  protect   -> capture-baseline   establish verified recovery evidence
  analyze   -> analyze            inspect the workspace and recovery needs
  preview   -> plan               show exactly what recovery would restore
  recover   -> execute            apply an approved recovery (explicit approval)
  verify    -> verify             independently validate the result
  status    -> status             workspace + support verdict
  doctor    -> probe              engine/runtime health check

The canonical engine commands (``capture-baseline``, ``plan``, ``execute``, ...)
are also accepted directly so the CLI, the engine and the extension share one
vocabulary.

Machine/agent use: add ``--json`` to emit the exact same structured envelope the
VS Code extension consumes.

This runner does NOT bundle a Python interpreter. It needs Python 3.11-3.14
because the engine's import closure is standard-library-only. See
``docs/operations/TERMINAL_RUNNER.md`` for installation and distribution.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path
from typing import Any

CLI_NAME = "interlock"
CLI_VERSION = "4.0.0"  # kept aligned with the engine / pyproject version

# Friendly product operation -> canonical bridge command (single source of truth).
ALIASES = {
    "protect": "capture-baseline",
    "preview": "plan",
    "recover": "execute",
    "doctor": "probe",
    "help": "help",
    "version": "version",
}

COMMANDS = ["probe", "status", "analyze", "capture-baseline", "plan", "execute", "verify"]

# Exit codes re-exported from the bridge so both interfaces agree exactly.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INTERNAL = 8
EXIT_PRECONDITION = 7
EXIT_CANCELLED = 130


# --------------------------------------------------------------- bridge loading


def _candidate_bridge_paths() -> list[Path]:
    """Where the shared orchestration module may live, in priority order."""
    paths: list[Path] = []
    env = os.environ.get("INTERLOCK_BRIDGE")
    if env:
        paths.append(Path(env))
    here = Path(__file__).resolve().parent
    # Source checkout: the bridge ships with the VS Code extension but is the
    # shared engine command layer for BOTH interfaces.
    paths.append(here / "extensions" / "vscode" / "python" / "interlock_bridge.py")
    # Installed data location (used by a bundled distribution).
    paths.append(Path(sys.prefix) / "share" / "intentlock" / "python" / "interlock_bridge.py")
    return paths


def load_bridge() -> Any:
    """Import the shared bridge module, or fail with an actionable message."""
    for candidate in _candidate_bridge_paths():
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("interlock_bridge", candidate)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules["interlock_bridge"] = module
                spec.loader.exec_module(module)
                return module
    # Last resort: an installed importable module.
    try:
        import interlock_bridge

        return interlock_bridge
    except Exception:  # noqa: S110 - probe; failure falls through to SystemExit below
        pass
    raise SystemExit(
        f"{CLI_NAME}: the shared recovery engine command layer (interlock_bridge.py) "
        "was not found.\n"
        "Set INTERLOCK_BRIDGE=/path/to/interlock_bridge.py, or run from an Interlock "
        "source checkout, or install a distribution that bundles it.\n"
        "See docs/operations/TERMINAL_RUNNER.md."
    )


# ------------------------------------------------------------------- rendering


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)


def _yes_no(value: Any) -> str:
    return "yes" if value else "no"


def _short(hash_value: Any, n: int = 12) -> str:
    if not hash_value:
        return "(none)"
    text = str(hash_value)
    return text[:n] + ("..." if len(text) > n else "")


def render_human(command: str, result: dict[str, Any], style: Style) -> str:
    """Terminal-friendly rendering for one successful engine result."""
    lines: list[str] = []

    def row(label: str, value: str) -> None:
        lines.append(f"  {style.dim(label + ':'):<22}{value}")

    if command in ("probe", "status"):
        engine = result.get("engine") or {}
        python = result.get("python") or {}
        support = result.get("support") or {}
        row(
            "Engine",
            style.green("available") if engine.get("available") else style.red("unavailable"),
        )
        if engine.get("version"):
            row("Engine version", str(engine.get("version")))
        row("Engine root", str(engine.get("root", "(unknown)")))
        row("Python", f"{python.get('version', '?')} ({python.get('executable', '?')})")
        if "workspace" in result:
            row("Workspace", str(result.get("workspace")))
        status = str(support.get("status", "unknown"))
        colour = style.green if status == "tested_primary" else style.yellow
        row("Support", colour(status) + f" - {support.get('detail', '')}")
        for warning in result.get("warnings", []) or []:
            lines.append(f"  {style.yellow('!')} {warning}")

    elif command == "analyze":
        scan = result.get("scan") or {}
        row("Workspace", str(result.get("workspace")))
        row("Files scanned", str(scan.get("file_count", scan.get("files_scanned", "?"))))
        row(
            "Confinement",
            style.green("pass") if result.get("confinement_pass") else style.red("FAIL"),
        )
        row("Can recover", _yes_no(result.get("adapter_can_recover")))
        findings = result.get("findings") or []
        if findings:
            lines.append(f"  {style.bold('Findings')}")
            for finding in findings[:12]:
                severity = str(finding.get("severity", "info"))
                colour = {"error": style.red, "warning": style.yellow}.get(severity, style.dim)
                lines.append(f"    {colour(severity):<8}{finding.get('message', '')}")
        else:
            lines.append(f"  {style.green('No findings.')}")

    elif command == "capture-baseline":
        row("Resource", str(result.get("resource")))
        row("Workspace", str(result.get("workspace")))
        row("Baseline sha256", _short(result.get("hash"), 16))
        row("Size", f"{result.get('size', '?')} bytes")
        row("Captured at", str(result.get("captured_at", "?")))
        snapshot = result.get("snapshot") or {}
        row("Kind", "binary" if snapshot.get("binary") else "text")
        lines.append(
            f"  {style.green('Protected.')} Run "
            f"{style.bold(CLI_NAME + ' preview')} after a change to see what recovery restores."
        )

    elif command == "plan":
        row("Resource", str(result.get("resource")))
        row("Operation", str(result.get("operation", "restore")))
        changed = not result.get("matches_baseline", True)
        row("Changed since baseline", style.yellow("yes") if changed else "no")
        diff = result.get("diff") or {}
        row("Diff", "changed" if diff.get("changed") else "identical")
        would = result.get("would_succeed", False)
        row("Recovery would succeed", style.green("yes") if would else style.red("no"))
        row("Conflict", str(result.get("conflict_status", "?")))
        row("Drift", str(result.get("drift_status", "?")))
        row("Approval required", style.yellow("yes") if result.get("requires_approval") else "no")
        baseline = result.get("baseline") or {}
        row("Baseline sha256", _short(baseline.get("hash"), 16))
        row("Evidence file", str(result.get("evidence_file", "(none)")))
        for warning in result.get("warnings", []) or []:
            lines.append(f"  {style.yellow('!')} {warning}")
        if would:
            resource = result.get("resource")
            evidence = result.get("evidence_file")
            apply_cmd = f"{CLI_NAME} recover --resource {resource} --evidence-file {evidence} --approved-by <you>"
            lines.append(f"  Review the diff, then apply with: {style.bold(apply_cmd)}")

    elif command == "execute":
        row("Resource", str(result.get("resource")))
        row("Approved by", str(result.get("approved_by", "(required)")))
        row("Execution state", str(result.get("execution_state", "?")))
        independent = result.get("independent_check") or {}
        row("File exists", _yes_no(independent.get("file_exists")))
        row("Byte-exact", style.green("yes") if independent.get("byte_exact") else style.red("no"))
        row("Expected sha256", _short(independent.get("expected_hash"), 16))
        row("Actual sha256", _short(independent.get("actual_hash"), 16))
        row("Engine verified", _yes_no(result.get("verified")))
        if result.get("success"):
            lines.append(f"  {style.green('Recovery applied and independently verified.')}")
        else:
            lines.append(
                f"  {style.red('Recovery did NOT verify.')} {result.get('adapter_error') or ''}"
            )

    elif command == "verify":
        row("Resource", str(result.get("resource")))
        independent = result.get("independent_check") or {}
        row("Matches baseline", _yes_no(result.get("matches_baseline")))
        row("Conflict", str(result.get("conflict_status", "?")))
        row("Byte-exact", style.green("yes") if independent.get("byte_exact") else style.red("no"))
        if result.get("success"):
            lines.append(f"  {style.green('Verified: file matches the protected baseline.')}")
        else:
            lines.append(f"  {style.red('Verification FAILED: file does not match the baseline.')}")

    else:
        for key, value in result.items():
            row(str(key), str(value))

    return "\n".join(lines)


# ------------------------------------------------------------------ invocator


def _build_envelope(bridge: Any, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Run one engine command and return (envelope, exit_code).

    Mirrors the bridge's own ``main()`` error-to-exit-code mapping so the CLI
    and the extension report identical codes, without duplicating any recovery
    logic (the work is all done inside the bridge's ``cmd_*`` handlers).
    """
    command = args.command
    base = {
        "bridge": getattr(bridge, "BRIDGE_NAME", "interlock-bridge"),
        "bridge_version": getattr(bridge, "BRIDGE_VERSION", "?"),
        "cli": CLI_NAME,
        "cli_version": CLI_VERSION,
        "command": command,
    }
    try:
        result = asyncio.run(bridge.dispatch(args))
        envelope = {**base, "ok": True, "result": result, "error": None}
        return envelope, bridge.EXIT_OK
    except bridge.EngineOutcome as outcome:
        envelope = {
            **base,
            "ok": False,
            "result": outcome.outcome,
            "error": {
                "kind": (
                    "verification_failed"
                    if outcome.exit_code == bridge.EXIT_VERIFICATION_FAILED
                    else "engine_refusal"
                ),
                "message": (
                    "Verification did not confirm a byte-exact restore."
                    if outcome.exit_code == bridge.EXIT_VERIFICATION_FAILED
                    else "The engine refused the recovery."
                ),
                "hint": "",
            },
        }
        return envelope, outcome.exit_code
    except bridge.BridgeError as exc:
        envelope = {
            **base,
            "ok": False,
            "result": None,
            "error": {"kind": exc.kind, "message": exc.message, "hint": exc.hint},
        }
        return envelope, exc.exit_code
    except Exception as exc:  # noqa: BLE001 - last-resort structured reporting
        envelope = {
            **base,
            "ok": False,
            "result": None,
            "error": {
                "kind": "internal_error",
                "message": f"{type(exc).__name__}: {exc}",
                "hint": "",
            },
        }
        return envelope, bridge.EXIT_INTERNAL


def _terminal_hint(hint: str) -> str:
    """Translate extension-specific guidance into terminal equivalents.

    The shared bridge emits hints written for the VS Code UI (it is the single
    source of truth for engine messages). For the terminal we substitute the
    CLI's own equivalent so the error stays actionable here too. This is
    presentation only - it never touches recovery logic or the message source.
    """
    lowered = hint.lower()
    if "capture baseline" in lowered or "interlock: capture" in lowered:
        return "Capture one first: interlock protect --workspace <dir> --resource <path>"
    if "interlock.engineroot" in lowered:
        return (
            "Point at an engine checkout with --engine-root <dir>, "
            "or install the intentlock package so the engine resolves from site-packages."
        )
    return hint


def _fail(message: str, code: int, style: Style, hint: str = "") -> int:
    print(f"{style.red('error:')} {message}", file=sys.stderr)
    if hint:
        print(f"  {style.dim(hint)}", file=sys.stderr)
    return code


def _default_baseline_path(workspace: str, resource: str) -> Path:
    """Private, out-of-project default location for captured evidence."""
    digest = (
        __import__("hashlib")
        .sha256(str(Path(workspace).resolve()).encode("utf-8"))
        .hexdigest()[:12]
    )
    safe_resource = resource.replace("\\", "_").replace("/", "_")
    return Path.home() / ".interlock" / "baselines" / f"{digest}-{safe_resource}.json"


class BaselineExistsError(RuntimeError):
    """Raised when a baseline already exists at the target path.

    The existing baseline is the last known-good before-state: it is never
    replaced by an ordinary capture.
    """


def _publish_new_file(target: Path, payload: str) -> None:
    """Publish *payload* at *target* atomically, never replacing an existing file.

    The content is written to a unique temporary file in the target's own
    directory (same filesystem), flushed and fsynced, and only then published.
    The publish itself is an exclusive, atomic operation: when the target
    already exists the operation fails and the existing file is left byte-for-
    byte untouched. That also makes two concurrent captures of the same
    resource safe: exactly one of them wins, the other is told the baseline
    already exists (there is no existence check that could race).

    Filesystems without hard-link support fall back to an exclusive
    create-reservation of the target followed by an atomic replace of that
    reservation, which keeps the same "never replace an existing baseline"
    guarantee.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        try:
            os.link(str(tmp), str(target))
        except FileExistsError:
            tmp.unlink(missing_ok=True)
            raise BaselineExistsError(str(target)) from None
        except OSError:
            # No hard-link support here: reserve the target exclusively first.
            try:
                reserved = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                tmp.unlink(missing_ok=True)
                raise BaselineExistsError(str(target)) from None
            os.close(reserved)
            try:
                os.replace(str(tmp), str(target))
            except BaseException:
                # Only ever remove the reservation this call created.
                with contextlib.suppress(OSError):
                    target.unlink(missing_ok=True)
                raise
    finally:
        # Clean up our own temporary file; never touch anything else.
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def _persist_baseline(result: dict[str, Any], out: str | None, bridge: Any) -> Path:
    """Write the engine's sealed baseline document to disk, atomically.

    The engine seals the baseline document (``baseline_document`` in the
    capture result); this function stores exactly that document - it never
    builds one itself - and refuses to store a document whose seal does not
    verify. An existing baseline is never replaced by an ordinary capture: the
    last known-good before-state is preserved and the caller is told why.
    """
    import json

    document = result.get("baseline_document")
    if not isinstance(document, dict):
        raise RuntimeError(
            "the engine did not return a sealed baseline document; nothing was written"
        )
    # Never persist a document the engine would refuse to use.
    bridge.verify_baseline_document(document)

    workspace = str(result.get("workspace", ""))
    resource = str(result.get("resource", ""))
    target = Path(out).expanduser() if out else _default_baseline_path(workspace, resource)
    payload = json.dumps(document, ensure_ascii=False, default=str)
    _publish_new_file(target, payload)
    return target


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Colour: on for a TTY unless disabled.
    style = Style(sys.stdout.isatty() and not os.environ.get("NO_COLOR"))

    # Translate friendly aliases to the canonical engine command (single source
    # of truth: the same command the extension drives).
    if argv and argv[0] in ALIASES:
        alias = argv[0]
        if alias == "help":
            argv[0] = "--help"
        elif alias == "version":
            argv[0] = "--version"
        else:
            argv[0] = ALIASES[alias]

    if not argv or argv[0] in ("-h", "--help"):
        print(_usage(style))
        return EXIT_OK if argv else _fail("no command given", EXIT_USAGE, style, _usage(style))

    if argv[0] in ("-V", "--version"):
        print(f"{CLI_NAME} {CLI_VERSION}")
        return EXIT_OK

    bridge = load_bridge()

    # Reuse the bridge's parser (identical flags/semantics) and add CLI-only ones.
    parser = bridge.build_parser()
    parser.prog = CLI_NAME
    parser.add_argument(
        "--json", action="store_true", help="emit the machine-readable engine envelope"
    )
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    parser.add_argument(
        "--out",
        default=None,
        help="where 'protect' writes the baseline evidence file (default: ~/.interlock/baselines/)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or EXIT_USAGE)

    if args.no_color:
        style = Style(False)

    if args.command not in COMMANDS:
        return _fail(f"unknown command: {args.command}", EXIT_USAGE, style, _usage(style))

    envelope, code = _build_envelope(bridge, args)

    if args.json:
        import json

        print(json.dumps(envelope, ensure_ascii=False, default=str))
        return code

    if envelope["ok"]:
        result = envelope.get("result") or {}
        print(f"{style.bold(CLI_NAME)} {style.cyan(args.command)}")
        print(render_human(args.command, result, style))
        # 'protect' persists the captured evidence so the other commands can use
        # it. This mirrors what the VS Code extension does with its own store:
        # the engine's sealed document is stored verbatim, atomically, and an
        # existing baseline is never replaced by an ordinary capture.
        baseline_path = None
        if args.command == "capture-baseline" and not args.json:
            try:
                baseline_path = _persist_baseline(result, args.out, bridge)
            except BaselineExistsError:
                print(
                    f"{style.red('error:')} a baseline already exists at that location; it was "
                    "left untouched. The last known-good before-state is never replaced by an "
                    "ordinary capture.",
                    file=sys.stderr,
                )
                print(
                    f"  {style.dim('Use --out <other-path> to capture a separate baseline, or move the existing file yourself.')}",
                    file=sys.stderr,
                )
                return EXIT_PRECONDITION
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                print(
                    f"{style.red('error:')} the baseline was captured but could not be saved: {exc}",
                    file=sys.stderr,
                )
                return EXIT_INTERNAL
        if baseline_path is not None:
            print(
                f"  {style.dim('Baseline saved:')} {baseline_path}\n"
                f'  {style.dim("Use it with:")} --baseline-file "{baseline_path}"'
            )
        return code

    error = envelope.get("error") or {}
    exit_code = _fail(str(error.get("message", "failed")), code, style)
    hint = error.get("hint")
    if hint:
        print(f"  {style.dim(_terminal_hint(str(hint)))}", file=sys.stderr)
    # Show any partial result the engine produced (e.g. an execution outcome).
    partial = envelope.get("result")
    if isinstance(partial, dict) and partial:
        print(render_human(args.command, partial, style))
    return exit_code


def _usage(style: Style) -> str:
    canonical = ", ".join(COMMANDS)
    return (
        f"{style.bold('Interlock Terminal Runner')} {CLI_VERSION} - recover files with verified evidence\n"
        f"\n"
        f"  {style.bold('usage:')} {CLI_NAME} <operation> --workspace <dir> --resource <path> [options]\n"
        f"\n"
        f"  {style.bold('operations')}\n"
        f"    protect    establish verified recovery evidence (capture-baseline)\n"
        f"    analyze    inspect the workspace and recovery needs\n"
        f"    preview    show exactly what recovery would restore (plan)\n"
        f"    recover    apply an approved recovery - requires --approved-by\n"
        f"    verify     independently validate the resulting file\n"
        f"    status     workspace and platform support verdict\n"
        f"    doctor     engine and runtime health check\n"
        f"\n"
        f"  {style.bold('options')}\n"
        f"    --workspace <dir>        target workspace (required for most operations)\n"
        f"    --resource <path>        file to protect/recover (relative to the workspace)\n"
        f"    --baseline-file <path>   stored evidence from 'protect'\n"
        f"    --evidence-file <path>   preview evidence (from 'preview')\n"
        f"    --approved-by <identity> explicit approver for 'recover'\n"
        f"    --engine-root <dir>      Interlock engine checkout (optional)\n"
        f"    --out <path>             where 'protect' writes the baseline\n"
        f"    --json                   machine-readable engine envelope\n"
        f"    --no-color               disable colour\n"
        f"\n"
        f"  {style.dim('Baselines:')} every baseline is sealed by the engine and verified\n"
        f"  {style.dim('             ')} before use. 'protect' never replaces an existing\n"
        f"  {style.dim('             ')} baseline: it refuses (exit 7) and preserves it. Use\n"
        f"  {style.dim('             ')} --out <other-path> to keep a second snapshot.\n"
        f"\n"
        f"  {style.dim('Exit codes:')} 0 ok, 2 usage, 3 engine unavailable, 4 not authorized,\n"
        f"  {style.dim('             ')} 5 refused, 6 verification failed, 7 precondition, 8 internal, 130 cancelled\n"
        f"\n"
        f"  {style.dim('Shares one engine with the VS Code extension:')} {canonical}\n"
    )


def console_entry() -> None:
    """Entry point for the installed ``interlock`` console script.

    Mirrors running ``python interlock_cli.py`` directly: the return value of
    ``main()`` becomes the process exit code, and Ctrl-C exits 130 (cancelled).
    """
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ncancelled.", file=sys.stderr)
        sys.exit(EXIT_CANCELLED)


if __name__ == "__main__":
    console_entry()
