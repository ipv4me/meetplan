from app import create_app, db
from app.models import User, Event, MeetingRequest, Status, EventParticipant

app = create_app()


@app.shell_context_processor
def make_shell_context():
    """Контекст для `flask shell` — удобно отлаживать модели."""
    return {
        "db": db,
        "User": User,
        "Event": Event,
        "MeetingRequest": MeetingRequest,
        "Status": Status,
        "EventParticipant": EventParticipant,
    }


if __name__ == "__main__":
    # 5000 на macOS обычно занят сервисом AirPlay Receiver, поэтому 5001
    app.run(debug=True, port=5001)
