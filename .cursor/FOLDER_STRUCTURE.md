spoon/
├── app/
│   ├── main.py                 # FastAPI app
│   ├── config.py               # env loading
│   ├── models.py               # Pydantic models
│   ├── routes.py               # API endpoints
│   │
│   ├── connectors/
│   │   ├── base.py
│   │   ├── gmail.py
│   │   ├── outlook.py
│   │   ├── slack.py
│   │   ├── notion.py
│   │   ├── linear.py
│   │   └── gdrive.py
│   │
│   └── supermemory/
│       ├── client.py
│       ├── ingest.py
│       └── search.py
│
├── tests/
│
├── requirements.txt
├── .env
├── .env.example
├── Dockerfile
├── Makefile
└── README.md
