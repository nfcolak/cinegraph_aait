"""Modal deployment of the CineGraph API.

One-time data load (downloads the course dataset from Google Drive into a Modal volume):
    modal run server/modal_app.py::fetch_data

Deploy / redeploy the API:
    modal deploy server/modal_app.py

The web app on Vercel proxies /api/* to the URL printed by `modal deploy`.
"""

from pathlib import Path

import modal

APP_NAME = "cinegraph-api"
ROOT = "/root/app"
DATA = f"{ROOT}/data"

# Google Drive file ids of the dataset (folder 18eRlonZRa79zP92tKdmycSnb1gCR0Bkz, shared by link)
DRIVE_FILES = {
    "graph.nt": "1DWdUcuM5upOUXfqlQJpmi_ghBHYm9jvz",
    "additional/images.json": "1U-sR5d-ksIiVtMg16B3SHGyuvVpRdNEb",
    "ratings/item_ratings.csv": "1OfoDwrxoUNTcXEmwWwn-IuWcmIA_qtiN",
    "embeddings/entity_embeds.npy": "1TRsLanal_7ObtsvcoKGPx7dweUXMxo67",
    "embeddings/entity_ids.del": "1wBuyiuJODUDJN1vcSkSZEaIdUHaNwrv0",
    "embeddings/relation_embeds.npy": "1drZYQI2SooQxoBDFGKuYpk8ifMyDG0vY",
    "embeddings/relation_ids.del": "1t-CF6Ty1KJ-pKbgkJSmzb9GOaVp3RCRm",
}

app = modal.App(APP_NAME)
volume = modal.Volume.from_name("cinegraph-data", create_if_missing=True)

base = modal.Image.debian_slim(python_version="3.11").pip_install(
    "rdflib==7.6.0", "numpy>=2,<3", "fastapi>=0.115", "pydantic>=2"
)

if modal.is_local():
    _repo = Path(__file__).resolve().parents[1]
    api_image = (
        base.env({"PYTHONPATH": ROOT, "PYTHONUNBUFFERED": "1"})
        .add_local_dir(str(_repo / "core"), f"{ROOT}/core")
        .add_local_dir(str(_repo / "server"), f"{ROOT}/server", ignore=["__pycache__", "modal_app.py"])
    )
else:
    api_image = base.env({"PYTHONPATH": ROOT, "PYTHONUNBUFFERED": "1"})


@app.function(image=modal.Image.debian_slim(python_version="3.11").pip_install("gdown>=5"), volumes={DATA: volume}, timeout=3600)
def fetch_data(force: bool = False):
    import os
    import subprocess

    for rel, file_id in DRIVE_FILES.items():
        dest = os.path.join(DATA, rel)
        if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
            print(f"skip {rel} ({os.path.getsize(dest)} bytes)")
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        subprocess.run(["gdown", file_id, "-O", dest + ".part", "-q"], check=True)
        os.replace(dest + ".part", dest)
        print(f"got {rel} ({os.path.getsize(dest)} bytes)")
    volume.commit()


@app.cls(
    image=api_image,
    volumes={DATA: volume},
    cpu=2.0,
    memory=6144,
    timeout=120,
    scaledown_window=300,
    max_containers=1,
    # The graph takes ~90 s to parse on Modal CPUs; a memory snapshot taken after
    # loading lets later cold starts restore the parsed graph instead.
    enable_memory_snapshot=True,
)
@modal.concurrent(max_inputs=16)
class Web:
    @modal.enter(snap=True)
    def load(self):
        import os

        os.chdir(ROOT)
        from server.api import warm

        warm()

    @modal.asgi_app()
    def web(self):
        from server.api import create_app

        return create_app(load_on_startup=False)
