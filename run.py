import os

from app import create_app, db
from app.models import User, Event, MeetingRequest, Status, EventParticipant

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "User": User,
        "Event": Event,
        "MeetingRequest": MeetingRequest,
        "Status": Status,
        "EventParticipant": EventParticipant,
    }


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=debug, port=port)
