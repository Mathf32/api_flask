from app import create_app
from dotenv import load_dotenv
import os


app = create_app()

if __name__ == "__main__":
    load_dotenv()
    app.run(debug=True)