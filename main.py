"""Application entry point.

Usage:
    # Run the server
    uvicorn main:app --reload --port 8000

    # Initialize the database
    python main.py init-db

    # Run the training pipeline on all unprocessed calls
    python main.py run-pipeline
"""
import sys

from app.factory import create_app

# This is what uvicorn imports
app = create_app()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Call Booking Bot CLI")
    parser.add_argument(
        "command",
        choices=["init-db", "run-pipeline", "serve"],
        help="Command to run",
    )
    args = parser.parse_args()

    if args.command == "init-db":
        from app.database import init_db
        init_db()
        print("Database initialised successfully.")

    elif args.command == "run-pipeline":
        from app.database import SessionLocal
        from app.models import CallLog
        from app.training import run_pipeline

        db = SessionLocal()
        try:
            # Process all calls that haven't been scored yet
            unprocessed = db.query(CallLog).filter(
                CallLog.quality_score == None,
                CallLog.training_consent == True,
            ).all()
            print(f"Processing {len(unprocessed)} call logs...")
            for call in unprocessed:
                run_pipeline(call.id, db)
            print("Done.")
        finally:
            db.close()

    elif args.command == "serve":
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
