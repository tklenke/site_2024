# ABOUTME: Tests which addresses nginx redirects and which it serves.
# ABOUTME: Runs the site's nginx config in the image that docker-compose.yaml names.

import http.client
import re
import ssl
import subprocess
import time
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent
CONF = SITE / "server" / "nginx_all_apps.conf"
CHALLENGE = "/.well-known/acme-challenge/token"
TIMEOUT = 20


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True,
                          timeout=60).stdout.strip()


def published_port(strContainer, intPort):
    return int(docker("port", strContainer, str(intPort)).splitlines()[0].rsplit(":", 1)[1])


@pytest.fixture(scope="module")
def ports(tmp_path_factory):
    """The local ports of a running nginx. Nothing listens where it expects flask."""
    strImage = re.search(r"image: (nginx:\S+)", (SITE / "docker-compose.yaml").read_text())[1]
    pathRun = tmp_path_factory.mktemp("nginx")
    pathSsl = pathRun / "ssl"
    pathSsl.mkdir()
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=m24tom.com", "-keyout", pathSsl / "privkey.pem",
                    "-out", pathSsl / "fullchain.pem"], check=True, capture_output=True)
    pathChallenge = pathRun / "www" / CHALLENGE.lstrip("/")
    pathChallenge.parent.mkdir(parents=True)
    pathChallenge.write_text("challenge")
    strContainer = docker("run", "-d", "--add-host", "flask:127.0.0.1",
                          "-p", "127.0.0.1::80", "-p", "127.0.0.1::443",
                          "-v", f"{CONF}:/etc/nginx/nginx.conf:ro",
                          "-v", f"{pathSsl}:/var/www/ssl:ro",
                          "-v", f"{pathRun / 'www'}:/var/www/certbot:ro", strImage)
    try:
        dctPorts = {"http": published_port(strContainer, 80),
                    "https": published_port(strContainer, 443)}
        wait_until_answering(dctPorts)
        yield dctPorts
    finally:
        docker("rm", "-f", strContainer)


def wait_until_answering(dctPorts):
    fEnd = time.monotonic() + TIMEOUT
    while True:
        try:
            return get(dctPorts, "https", "m24tom.com", "/")
        except (OSError, http.client.HTTPException):
            if time.monotonic() > fEnd:
                raise
            time.sleep(.2)


def get(dctPorts, strScheme, strHost, strPath):
    """The status, the Location header and the body of the answer to a request."""
    if strScheme == "http":
        connection = http.client.HTTPConnection("127.0.0.1", dctPorts["http"], timeout=5)
    else:
        connection = http.client.HTTPSConnection("127.0.0.1", dctPorts["https"], timeout=5,
                                                 context=ssl._create_unverified_context())
    try:
        connection.request("GET", strPath, headers={"Host": strHost})
        response = connection.getresponse()
        return response.status, response.getheader("Location"), response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("strScheme, strHost", [
    ("http", "m24tom.com"), ("http", "www.m24tom.com"), ("https", "www.m24tom.com")])
def test_redirects_to_the_one_name_in_one_hop(ports, strScheme, strHost):
    intStatus, strLocation, _ = get(ports, strScheme, strHost, "/x/y?a=b")
    assert (intStatus, strLocation) == (301, "https://m24tom.com/x/y?a=b")


@pytest.mark.parametrize("strHost", ["m24tom.com", "localhost"])
def test_the_one_name_is_passed_to_flask(ports, strHost):
    # 502: nothing listens where nginx expects flask
    assert get(ports, "https", strHost, "/x")[:2] == (502, None)


def test_www_serves_no_images(ports):
    assert get(ports, "https", "www.m24tom.com", "/cgimages/x")[0] == 301


def test_images_are_served_by_nginx(ports):
    assert get(ports, "https", "m24tom.com", "/cgimages/x")[0] == 404


@pytest.mark.parametrize("strHost", ["m24tom.com", "www.m24tom.com"])
def test_the_certificate_challenge_is_answered_for_both_names(ports, strHost):
    intStatus, _, binBody = get(ports, "http", strHost, CHALLENGE)
    assert (intStatus, binBody) == (200, b"challenge")
