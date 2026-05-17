from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from hello_cloud_agent.agent import HELLO_RESPONSE, root_agent


def main() -> None:
    app_name = "hello_cloud_agent"
    user_id = "prompt07-local"
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(app_name=app_name, user_id=user_id)
    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="hello")],
    )

    texts: list[str] = []
    for event in runner.run(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        if event.content and event.content.parts:
            texts.extend(part.text for part in event.content.parts if part.text)

    response = "".join(texts).strip()
    print(response)
    if response != HELLO_RESPONSE:
        raise SystemExit(f"unexpected response: {response!r}")


if __name__ == "__main__":
    main()
