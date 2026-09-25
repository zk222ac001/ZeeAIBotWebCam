import os

import uvicorn

from robotic_classroom.core.config import load_settings


def run() -> None:
    settings = load_settings()
    certfile = os.getenv("UVICORN_SSL_CERTFILE") or None
    keyfile = os.getenv("UVICORN_SSL_KEYFILE") or None
    if bool(certfile) != bool(keyfile):
        raise RuntimeError(
            "Both UVICORN_SSL_CERTFILE and UVICORN_SSL_KEYFILE are required for HTTPS"
        )

    uvicorn.run(
        "robotic_classroom.web.app:app",
        host=settings.web.host,
        port=settings.web.port,
        reload=False,
        ssl_certfile=certfile,
        ssl_keyfile=keyfile,
    )


if __name__ == "__main__":
    run()
