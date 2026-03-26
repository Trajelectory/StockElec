import logging
from app import create_app

# Logs visibles dans le terminal (niveau INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = create_app()

if __name__ == "__main__":
    # use_reloader=False : évite que le reloader tue les threads d'enrichissement
    app.run(debug=True, use_reloader=False)
