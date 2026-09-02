import uvicorn

from robotic_classroom.core.config import load_settings


def run() -> None:
    settings = load_settings()
    uvicorn.run(
        "robotic_classroom.web.app:app",
        host=settings.web.host,
        port=settings.web.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
