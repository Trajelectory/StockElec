import logging
from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = create_app()

if __name__ == "__main__":
    try:
        from waitress import serve
        log = logging.getLogger("stockelec")
        log.info("StockElec démarré sur http://127.0.0.1:5000")
        serve(app, host="127.0.0.1", port=5000, threads=4)
    except ImportError:
        # Waitress pas installé — fallback sur le serveur Flask
        logging.getLogger("stockelec").warning(
            "Waitress non trouvé, utilisation du serveur de développement Flask.\n"
            "Installe-le avec : pip install waitress"
        )
        app.run(debug=False, use_reloader=False)
