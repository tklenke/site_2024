# ABOUTME: Tests sudo_renew_cert.sh against a scratch certbot directory tree.
# ABOUTME: A stand-in docker command records its calls; every file operation is real.

import functools
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
BOTH_NAMES = ("m24tom.com", "www.m24tom.com")
CURRENT_START = "20260101000000Z"
LATER_START = "20260301000000Z"


@functools.cache
def certificate(strStart, lstNames=BOTH_NAMES):
    """A real self-signed certificate that starts at the given time."""
    return subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
         "-noenc", "-keyout", "/dev/null", "-subj", "/CN=m24tom.com", "-addext",
         "subjectAltName=" + ",".join(f"DNS:{strName}" for strName in lstNames),
         "-not_before", strStart, "-not_after", "20300101000000Z"],
        check=True, capture_output=True, text=True).stdout


@pytest.fixture
def site(tmp_path):
    """A scratch site directory with a working certificate and two archived versions."""
    (tmp_path / LIVE).mkdir(parents=True)
    for strFile in CERT_FILES:
        (tmp_path / LIVE / strFile).write_text(f"current {strFile}\n")
    with open(tmp_path / LIVE / "fullchain.pem", "a") as f:
        f.write(certificate(CURRENT_START, ("m24tom.com",)))
    add_archive(tmp_path, "m24tom.com-0001", [1, 2])
    return tmp_path


def add_archive(pathSite, strDir, lstNumbers, strCertificate=None):
    """Adds numbered files to an archive directory, each with a first line that tells them apart."""
    pathDir = pathSite / ARCHIVE / strDir
    pathDir.mkdir(parents=True, exist_ok=True)
    if strCertificate is None:
        strCertificate = certificate(LATER_START)
    for intNumber in lstNumbers:
        (pathDir / f"fullchain{intNumber}.pem").write_text(
            f"{strDir} fullchain{intNumber}\n{strCertificate}")
        (pathDir / f"privkey{intNumber}.pem").write_text(f"{strDir} privkey{intNumber}\n")


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
    return (pathSite / LIVE / strFile).read_text().splitlines()[0]


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
    assert (site / ARCHIVE / "m24tom.com-0001" / "fullchain1.pem").read_text().startswith(
        "m24tom.com-0001 fullchain1\n")


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


# ---- both names
def test_certbot_is_asked_for_both_names(site):
    run_script(site, "y\ny\n")

    lstCertbot = [strCall for strCall in docker_calls(site) if "certonly" in strCall]
    assert len(lstCertbot) == 2
    for strCall in lstCertbot:
        assert strCall.endswith(" -d m24tom.com -d www.m24tom.com")
    assert ["--dry-run" in strCall for strCall in lstCertbot] == [True, False]


def test_both_addresses_are_to_be_checked(site):
    result = run_script(site, "y\ny\n")

    assert "Check https://m24tom.com and https://www.m24tom.com in your browser." in result.stdout


# ---- the certificate about to be installed
def assert_stopped_before_replacing(pathSite, result):
    assert result.returncode != 0
    assert_current_certificate_in_place(pathSite)
    assert sorted(p.name for p in (pathSite / LIVE).iterdir()) == list(CERT_FILES)
    assert not (pathSite / BACKUP).exists()
    assert "compose restart" not in docker_calls(pathSite)


@pytest.mark.parametrize("lstNames, strMissing", [
    (("m24tom.com",), "www.m24tom.com"),
    (("www.m24tom.com",), "m24tom.com"),
    (("m24tom.com", "www.m24tom.com.example.org"), "www.m24tom.com"),
    (("notm24tom.com", "www.m24tom.com"), "m24tom.com"),
    (("m24tom.com", "wwwxm24tom.com"), "www.m24tom.com")])
def test_a_certificate_without_both_names_is_not_installed(site, lstNames, strMissing):
    add_archive(site, "m24tom.com-0001", [3], certificate(LATER_START, lstNames))

    result = run_script(site, "y\ny\n")

    assert_stopped_before_replacing(site, result)
    assert (f"Error: {ARCHIVE}/m24tom.com-0001/fullchain3.pem does not name {strMissing}\n"
            in result.stdout)


def test_an_older_certificate_is_not_installed(site):
    add_archive(site, "m24tom.com-0002", [1], certificate("20251231235959Z"))

    result = run_script(site, "y\ny\n")

    assert_stopped_before_replacing(site, result)
    assert (f"Error: {ARCHIVE}/m24tom.com-0002/fullchain1.pem is older than the certificate in place"
            in result.stdout)


def test_the_certificate_in_place_can_be_installed_again(site):
    add_archive(site, "m24tom.com-0001", [3], certificate(CURRENT_START))

    result = run_script(site, "y\ny\n")

    assert result.returncode == 0
    assert live_text(site, "fullchain.pem") == "m24tom.com-0001 fullchain3"


def test_a_file_that_is_no_certificate_is_not_installed(site):
    add_archive(site, "m24tom.com-0001", [3], "no certificate")

    assert_stopped_before_replacing(site, run_script(site, "y\ny\n"))


@pytest.mark.parametrize("strContent", [None, "no certificate"])
def test_an_unreadable_certificate_in_place_stops_the_script(site, strContent):
    pathCurrent = site / LIVE / "fullchain.pem"
    pathCurrent.unlink()
    if strContent is not None:
        pathCurrent.write_text(strContent)

    result = run_script(site, "y\ny\n")

    assert result.returncode != 0
    assert "fullchain.pem" in result.stdout + result.stderr
    assert (pathCurrent.read_text() if pathCurrent.exists() else None) == strContent
    assert live_text(site, "privkey.pem") == "current privkey.pem"
    assert "compose restart" not in docker_calls(site)
