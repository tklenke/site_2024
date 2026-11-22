# ABOUTME: Tests sudo_renew_cert.sh against a scratch certbot directory tree.
# ABOUTME: A stand-in docker command records its calls; every file operation is real.

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "sudo_renew_cert.sh"
CONF = Path("server/certbot/conf")
LIVE = CONF / "live" / "m24tom.com"
BACKUP = CONF / "live" / "m24tom.com.old"
ARCHIVE = CONF / "archive"
CERT_FILES = ("fullchain.pem", "privkey.pem")


@pytest.fixture
def site(tmp_path):
    """A scratch site directory with a working certificate and two archived versions."""
    (tmp_path / LIVE).mkdir(parents=True)
    for strFile in CERT_FILES:
        (tmp_path / LIVE / strFile).write_text(f"current {strFile}")
    add_archive(tmp_path, "m24tom.com-0001", [1, 2])
    return tmp_path


def add_archive(pathSite, strDir, lstNumbers):
    pathDir = pathSite / ARCHIVE / strDir
    pathDir.mkdir(parents=True)
    for intNumber in lstNumbers:
        for strName in ("fullchain", "privkey"):
            (pathDir / f"{strName}{intNumber}.pem").write_text(f"{strDir} {strName}{intNumber}")


def run_script(pathSite, strAnswers, strFailOn="nothing"):
    """Run the script in pathSite. A docker call whose arguments contain strFailOn fails."""
    pathBin = pathSite / "bin"
    pathBin.mkdir()
    pathDocker = pathBin / "docker"
    pathDocker.write_text(
        '#!/bin/bash\n'
        f'echo "$*" >> "{pathSite}/docker_calls.txt"\n'
        f'[[ "$*" != *"{strFailOn}"* ]]\n')
    pathDocker.chmod(0o755)
    dctEnv = dict(os.environ, PATH=f"{pathBin}:{os.environ['PATH']}")
    return subprocess.run(["bash", str(SCRIPT)], cwd=pathSite, env=dctEnv, input=strAnswers,
                          capture_output=True, text=True, timeout=30)


def live_text(pathSite, strFile):
    return (pathSite / LIVE / strFile).read_text()


def docker_calls(pathSite):
    return (pathSite / "docker_calls.txt").read_text().splitlines()


def assert_current_certificate_in_place(pathSite):
    for strFile in CERT_FILES:
        assert live_text(pathSite, strFile) == f"current {strFile}"


def test_highest_numbered_files_are_put_in_place(site):
    result = run_script(site, "y\ny\n")

    assert result.returncode == 0
    assert result.stderr == ""
    assert live_text(site, "fullchain.pem") == "m24tom.com-0001 fullchain2"
    assert live_text(site, "privkey.pem") == "m24tom.com-0001 privkey2"
    assert sorted(p.name for p in (site / LIVE).iterdir()) == list(CERT_FILES)
    assert not (site / BACKUP).exists()
    assert docker_calls(site)[-1] == "compose restart"


def test_numbers_are_compared_as_numbers(site):
    add_archive(site, "m24tom.com-0009", [1])
    add_archive(site, "m24tom.com-0010", [2, 9, 10])

    run_script(site, "y\ny\n")

    assert live_text(site, "fullchain.pem") == "m24tom.com-0010 fullchain10"
    assert live_text(site, "privkey.pem") == "m24tom.com-0010 privkey10"


def test_symlinks_in_live_become_physical_files(site):
    for strFile in CERT_FILES:
        (site / LIVE / strFile).unlink()
        strArchived = strFile.replace(".pem", "1.pem")
        (site / LIVE / strFile).symlink_to(f"../../archive/m24tom.com-0001/{strArchived}")

    run_script(site, "y\ny\n")

    for strFile in CERT_FILES:
        assert not (site / LIVE / strFile).is_symlink()
    assert live_text(site, "fullchain.pem") == "m24tom.com-0001 fullchain2"
    assert (site / ARCHIVE / "m24tom.com-0001" / "fullchain1.pem").read_text() == \
        "m24tom.com-0001 fullchain1"


def test_permissions(site):
    run_script(site, "y\ny\n")

    assert stat.S_IMODE((site / LIVE / "privkey.pem").stat().st_mode) == 0o600
    assert stat.S_IMODE((site / LIVE / "fullchain.pem").stat().st_mode) == 0o644


@pytest.mark.parametrize("strMissing", ["fullchain*.pem", "privkey*.pem", "privkey2.pem", "*.pem"])
def test_missing_archive_files_leave_the_current_certificate(site, strMissing):
    for pathFile in (site / ARCHIVE / "m24tom.com-0001").glob(strMissing):
        pathFile.unlink()

    result = run_script(site, "y\ny\n")

    assert result.returncode != 0
    assert "Error" in result.stdout
    assert_current_certificate_in_place(site)
    assert "compose restart" not in docker_calls(site)


def test_missing_archive_directory_leaves_the_current_certificate(site):
    for pathFile in (site / ARCHIVE / "m24tom.com-0001").iterdir():
        pathFile.unlink()
    (site / ARCHIVE / "m24tom.com-0001").rmdir()

    result = run_script(site, "y\ny\n")

    assert result.returncode != 0
    assert "Error: No archive directory found" in result.stdout
    assert_current_certificate_in_place(site)


def test_unreadable_archive_file_leaves_the_current_certificate(site):
    (site / ARCHIVE / "m24tom.com-0001" / "privkey2.pem").chmod(0)

    result = run_script(site, "y\ny\n")

    assert result.returncode != 0
    assert "privkey2.pem" in result.stderr
    assert_current_certificate_in_place(site)
    assert "compose restart" not in docker_calls(site)


def test_failed_dry_run_stops_before_the_real_run(site):
    result = run_script(site, "y\ny\n", strFailOn="--dry-run")

    assert result.returncode != 0
    assert len(docker_calls(site)) == 1
    assert_current_certificate_in_place(site)


def test_failed_certbot_run_stops_before_touching_files(site):
    result = run_script(site, "y\ny\n", strFailOn="certbot/ -d")

    assert result.returncode != 0
    assert len(docker_calls(site)) == 2
    assert_current_certificate_in_place(site)


def test_answering_no_to_the_dry_run_aborts(site):
    result = run_script(site, "n\n")

    assert result.returncode == 1
    assert len(docker_calls(site)) == 1
    assert_current_certificate_in_place(site)


def test_answering_no_after_the_restart_rolls_back(site):
    result = run_script(site, "y\nn\n")

    assert result.returncode == 0
    assert "Rollback complete" in result.stdout
    assert_current_certificate_in_place(site)
    assert not (site / BACKUP).exists()
    assert docker_calls(site).count("compose restart") == 2


def test_failed_restart_still_offers_the_rollback(site):
    run_script(site, "y\nn\n", strFailOn="compose restart")

    assert_current_certificate_in_place(site)
