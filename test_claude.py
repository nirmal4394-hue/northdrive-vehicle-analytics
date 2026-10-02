import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
key = os.getenv("ANTHROPIC_API_KEY")
if not key:
    raise SystemExit("No ANTHROPIC_API_KEY found. Check your .env file is in the project folder.")

client = Anthropic(api_key=key)
reply = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=100,
    messages=[{"role": "user", "content": "Reply in one sentence: are you working?"}],
)
print("Claude says:", reply.content[0].text)