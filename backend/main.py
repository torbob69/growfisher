from fastapi import FastAPI
from script.main import chat

app = FastAPI()

@app.get("/test")
def test(text: str = "Hi welcome to torbob69's autofisher."):
    chat(text)
    return {"ok": True, "sent": text}