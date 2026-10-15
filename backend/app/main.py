from fastapi import FastAPI

app = FastAPI(title="Crochet by Carlen")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
