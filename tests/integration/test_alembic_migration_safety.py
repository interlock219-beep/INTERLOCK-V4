"""Migration safety tests on a disposable SQLite database only.

R6 (Phase 3 remediation): the test suite previously had zero alembic coverage.
These tests exercise the real migration chain against a throwaway database in
`tmp_path`: fresh upgrade, version stamp, idempotent second upgrade, and the
known schema-drift check.

Constraints honored:
- No production database is touched; `DATABASE_URL` points into `tmp_path`.
- The root `.env` is never read or modified (env var overrides `.env`).
- The M-PKG migration is NOT applied or created here (pending approval);
  `alembic check` drift (defect D3) is documented via non-strict xfail so the
  gate stays visible instead of being hidden or asserted-green.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic as a subprocess with an isolated DATABASE_URL."""
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(  # noqa: S603 - fixed argv, repo-local trusted interpreter
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=300,
    )


@pytest.fixture()
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'migrate_test.db'}"


class TestAlembicFreshUpgrade:
    def test_upgrade_head_on_fresh_disposable_db(self, sqlite_url: str) -> None:
        """A fresh database must migrate to head cleanly (exit 0)."""
        result = _run_alembic(sqlite_url, "upgrade", "head")
        assert result.returncode == 0, (
            f"upgrade head failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
        )

    def test_upgrade_stamps_single_head_revision(self, sqlite_url: str) -> None:
        _run_alembic(sqlite_url, "upgrade", "head")
        current = _run_alembic(sqlite_url, "current")
        assert current.returncode == 0
        heads = _run_alembic(sqlite_url, "heads")
        assert heads.returncode == 0
        # `alembic current` must reference exactly one revision line.
        revision_lines = [
            line for line in current.stdout.splitlines() if line.strip() and "(" in line
        ]
        assert len(revision_lines) == 1, revision_lines

    def test_second_upgrade_is_idempotent(self, sqlite_url: str) -> None:
        first = _run_alembic(sqlite_url, "upgrade", "head")
        assert first.returncode == 0
        second = _run_alembic(sqlite_url, "upgrade", "head")
        assert second.returncode == 0
        assert "already" in (second.stdout + second.stderr).lower() or second.returncode == 0

    @pytest.mark.xfail(
        reason=(
            "Confirmed defect D-MIG-1b (escalation of D-MIG-1, proved on 2 "
            "disposable databases 2026-10-17 via d_mig1_repro.py and "
            "d_mig1_booted_roundtrip.py): a FAILED `downgrade base` leaves the "
            "database permanently unrecoverable by alembic in BOTH directions. "
            "3cebbede5768.downgrade() is `pass`, so after 0010's downgrade "
            "fails (missing table/index), the `after_state_snapshot` column "
            "added by 3cebbede5768.upgrade() was never removed; the next "
            "`upgrade head` re-enters 3cebbede5768.upgrade() and dies with "
            "'duplicate column name: after_state_snapshot'. Neither "
            "downgrade nor upgrade can proceed (stuck at fc5e7844e4dd); "
            "recovery needs manual SQL surgery or backup restore. Fix is the "
            "approval-gated R10 repair. Kept visible as xfail."
        ),
        strict=False,
    )
    def test_failed_downgrade_must_not_brick_reupgrade(self, sqlite_url: str) -> None:
        """Forward recovery must survive a failed downgrade attempt."""
        assert _run_alembic(sqlite_url, "upgrade", "head").returncode == 0
        # D-MIG-1: this downgrade currently fails part-chain (that is the
        # already-xfail'd roundtrip test); this test checks what happens AFTER.
        _run_alembic(sqlite_url, "downgrade", "base")
        recovery = _run_alembic(sqlite_url, "upgrade", "head")
        assert recovery.returncode == 0, (
            "re-upgrade after failed downgrade must succeed "
            "(database must not be bricked):\n"
            f"{recovery.stdout[-1500:]}\n{recovery.stderr[-1500:]}"
        )

    @pytest.mark.xfail(
        reason=(
            "Confirmed defect D-MIG-1 (this test discovered it, 2026-10-17): full "
            "`downgrade base` is IMPOSSIBLE on any database, empty or populated. "
            "Migration 3cebbede5768 drops 8 tables in upgrade() but its downgrade() "
            "is `pass` (never recreates them); 0010's downgrade then fails dropping "
            "indexes on those non-existent tables (sqlite: no such index "
            "ix_recovery_reports_incident_id). Fixing requires rewriting a historical "
            "migration's downgrade (substantial DDL inverse) — APPROVAL REQUIRED "
            "(R10). Kept visible as xfail; not hidden, not asserted green."
        ),
        strict=False,
    )
    def test_downgrade_base_then_upgrade_head_roundtrip(self, sqlite_url: str) -> None:
        """Full downgrade→upgrade roundtrip on an empty database."""
        assert _run_alembic(sqlite_url, "upgrade", "head").returncode == 0
        down = _run_alembic(sqlite_url, "downgrade", "base")
        assert down.returncode == 0, (
            f"downgrade base on empty db failed:\n{down.stdout}\n{down.stderr}"
        )
        assert _run_alembic(sqlite_url, "upgrade", "head").returncode == 0

    @pytest.mark.xfail(
        reason=(
            "Confirmed D-MIG-1b PARTIAL-TRAVERSAL variant (proved on a disposable "
            "database 2026-10-18 via d_mig1_partial_probe.py): `downgrade "
            "fc5e7844e4dd` EXITS 0 while crossing 3cebbede5768, whose "
            "downgrade() is `pass`, so the after_state_snapshot column stays "
            "in place below the new stamp; the next `upgrade head` then dies "
            "with 'duplicate column name: after_state_snapshot'. A SUCCESSFUL "
            "downgrade therefore silently bricks forward recovery — strictly "
            "worse than the failed-downgrade variant above, because the "
            "operator is told the rollback worked. Repair is the "
            "approval-gated R10. Kept visible as xfail; never hidden."
        ),
        strict=False,
    )
    def test_successful_partial_downgrade_must_not_brick_reupgrade(
        self, sqlite_url: str
    ) -> None:
        """A rollback that reports success must remain forward-recoverable."""
        assert _run_alembic(sqlite_url, "upgrade", "head").returncode == 0
        down = _run_alembic(sqlite_url, "downgrade", "fc5e7844e4dd")
        assert down.returncode == 0, (
            "partial downgrade to fc5e7844e4dd unexpectedly failed:\n"
            f"{down.stdout}\n{down.stderr}"
        )
        recovery = _run_alembic(sqlite_url, "upgrade", "head")
        assert recovery.returncode == 0, (
            "re-upgrade after a SUCCESSFUL partial downgrade must succeed "
            "(database must not be bricked):\n"
            f"{recovery.stdout[-1500:]}\n{recovery.stderr[-1500:]}"
        )


class TestAlembicGraph:
    def test_single_head(self) -> None:
        """Migration graph must have exactly one head (regression for V5-21)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(  # noqa: S603 - fixed argv, repo-local trusted interpreter
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "heads"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            timeout=120,
        )
        assert result.returncode == 0
        head_lines = [line for line in result.stdout.splitlines() if "(head)" in line]
        assert len(head_lines) == 1, head_lines

    @pytest.mark.xfail(
        reason=(
            "Known defect D3 (gap register #1): model/migration drift (33 ops) until "
            "M-PKG is approved and applied. Kept visible as xfail — never hidden, "
            "never asserted green."
        ),
        strict=False,
    )
    def test_alembic_check_no_drift(self, sqlite_url: str) -> None:
        result = _run_alembic(sqlite_url, "check")
        assert result.returncode == 0, (
            f"alembic check reported drift:\n{result.stdout}\n{result.stderr}"
        )


class TestAlembicIndexConsistency:
    def test_index_names_match_models_after_fresh_upgrade(
        self, sqlite_url: str, tmp_path: Path
    ) -> None:
        """Mission §5 index-name consistency on a disposable upgraded database.

        Every model-declared index (columns with ``index=True`` ->
        ``ix_<table>_<col>``, plus explicit ``table.indexes`` entries) must
        exist under exactly that name for every table present in both the
        models and the database.

        Verified green on a disposable DB 2026-10-18 (30 registered tables, 0
        index mismatches), so this is a live regression guard, not an xfail.
        Model tables absent from the upgraded database (observed: the 8 tables
        dropped by migration 3cebbede5768, visible only once *all* model
        modules happen to be registered in the pytest process — registration
        order dependent, so deliberately not asserted here) are table-level
        drift covered by the D3 ``alembic check`` xfail above, not index-name
        drift.
        """
        import app.infrastructure.persistence.models  # noqa: F401 - registers all models
        from app.infrastructure.persistence.database import Base

        result = _run_alembic(sqlite_url, "upgrade", "head")
        assert result.returncode == 0

        db_file = tmp_path / "migrate_test.db"
        con = sqlite3.connect(str(db_file))
        try:
            db_tables = {
                row[0]
                for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            mismatches: list[str] = []
            for table in Base.metadata.tables.values():
                if table.name not in db_tables:
                    # Table-level drift (8 model-only tables) is D3 territory,
                    # covered by the alembic check xfail; see docstring.
                    continue
                expected = {f"ix_{table.name}_{c.name}" for c in table.columns if c.index}
                expected |= {i.name for i in table.indexes if i.name}
                rows = con.execute(  # noqa: S608 - identifier from Base.metadata, not user input
                    f"PRAGMA index_list('{table.name}')"
                ).fetchall()
                actual = {
                    row[1]
                    for row in rows
                    if not str(row[1]).startswith("sqlite_autoindex_")
                }
                if expected != actual:
                    mismatches.append(
                        f"{table.name}: model_only={sorted(expected - actual)} "
                        f"db_only={sorted(actual - expected)}"
                    )
        finally:
            con.close()

        assert not mismatches, (
            "index-name drift between models and migrations: " + "; ".join(mismatches)
        )
