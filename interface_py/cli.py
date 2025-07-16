"""Command line interface aggregating all scraping commands."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from interface_py.scrap_collection import scrape_collection
from interface_py.scraper_images import (
    download_images,
    _open_folder,
    ALT_JSON_PATH,
    USE_ALT_JSON,
)
from interface_py.constants import (
    IMAGES_DEFAULT_SELECTOR as DEFAULT_IMG_SELECTOR,
    COLLECTION_DEFAULT_SELECTOR,
    DEFAULT_NEXT_SELECTOR,
    DESCRIPTION_DEFAULT_SELECTOR,
    PRICE_DEFAULT_SELECTOR,
    VARIANT_DEFAULT_SELECTOR,
    USER_AGENT,
)
from interface_py.scrap_description import scrape_description
from interface_py.scrap_price import scrape_price
from interface_py.moteur_variante import scrape_variants
from gui.main_window import main as gui_main


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _run_collection(args: argparse.Namespace) -> None:
    if not args.url:
        args.url = input("Entrez l'URL de la collection a scraper : ").strip()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    scrape_collection(
        args.url,
        Path(args.output),
        args.selector,
        args.next_selector,
        args.format,
    )


def _run_images(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not args.alt_json_path:
        args.alt_json_path = None

    if args.url and args.urls:
        parser.error("--url et --urls sont mutuellement exclusifs")

    urls_list: list[str] = []
    if args.urls:
        try:
            with open(args.urls, "r", encoding="utf-8") as fh:
                urls_list = [line.strip() for line in fh if line.strip()]
        except OSError as exc:  # pragma: no cover - argument parsing
            parser.error(f"Impossible de lire le fichier {args.urls}: {exc}")

    if not urls_list:
        if not args.url:
            args.url = input("\U0001F517 Entrez l'URL du produit WooCommerce : ").strip()
        urls_list = [args.url]

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")

    if args.jobs > 1 and len(urls_list) > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    download_images,
                    url,
                    css_selector=args.selector,
                    parent_dir=args.parent_dir,
                    user_agent=args.user_agent,
                    use_alt_json=args.use_alt_json,
                    alt_json_path=args.alt_json_path,
                    max_threads=args.max_threads,
                ): url
                for url in urls_list
            }
            for fut in as_completed(futures):
                try:
                    info = fut.result()
                    if args.preview:
                        _open_folder(info["folder"])
                except ValueError as exc:
                    logging.error("Erreur : %s", exc)
    else:
        for url in urls_list:
            try:
                info = download_images(
                    url,
                    css_selector=args.selector,
                    parent_dir=args.parent_dir,
                    user_agent=args.user_agent,
                    use_alt_json=args.use_alt_json,
                    alt_json_path=args.alt_json_path,
                    max_threads=args.max_threads,
                )
                if args.preview:
                    _open_folder(info["folder"])
            except ValueError as exc:
                logging.error("Erreur : %s", exc)


def _run_description(args: argparse.Namespace) -> None:
    if not args.url:
        args.url = input("\U0001F517 Entrez l'URL du produit : ").strip()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    scrape_description(args.url, args.selector, Path(args.output))


def _run_price(args: argparse.Namespace) -> None:
    if not args.url:
        args.url = input("\U0001F517 Entrez l'URL du produit : ").strip()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    scrape_price(args.url, args.selector, Path(args.output))


def _run_variants(args: argparse.Namespace) -> None:
    if not args.url:
        args.url = input("URL du produit : ").strip()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    scrape_variants(args.url, args.selector, Path(args.output))


def _run_gui(args: argparse.Namespace) -> None:  # noqa: ARG001
    gui_main()


# ---------------------------------------------------------------------------
# Main parser builder
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Outils de scraping unifies")
    sub = parser.add_subparsers(dest="command", required=True)

    # Collection ------------------------------------------------------------
    p_col = sub.add_parser("collection", help="Scraper une collection")
    p_col.add_argument("url", nargs="?", help="URL de la page de collection (si absent, demande a l'execution)")
    p_col.add_argument("-o", "--output", default="products.txt", help="Chemin du fichier de sortie (defaut: %(default)s)")
    p_col.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    p_col.add_argument("-s", "--selector", default=COLLECTION_DEFAULT_SELECTOR, help="Selecteur CSS des liens produits (defaut: %(default)s)")
    p_col.add_argument("--next-selector", default=DEFAULT_NEXT_SELECTOR, help="Selecteur CSS du bouton 'page suivante' (defaut: %(default)s)")
    p_col.add_argument("--format", choices=["txt", "json", "csv"], default="txt", help="Format de sortie : txt, json ou csv (defaut: %(default)s)")
    p_col.set_defaults(func=_run_collection)

    # Images ---------------------------------------------------------------
    p_img = sub.add_parser("images", help="Telecharger les images d'un produit")
    p_img.add_argument("url", nargs="?", help="URL du produit (si absent, demande a l'execution)")
    p_img.add_argument("-s", "--selector", default=DEFAULT_IMG_SELECTOR, help="Selecteur CSS des images (defaut: %(default)s)")
    p_img.add_argument("-d", "--dest", "--parent-dir", dest="parent_dir", default="images", help="Dossier parent des images (defaut: %(default)s)")
    p_img.add_argument("--urls", help="Fichier contenant une liste d'URLs (une par ligne)")
    p_img.add_argument("--preview", action="store_true", help="Ouvrir le dossier des images apres telechargement")
    p_img.add_argument("--user-agent", default=USER_AGENT, help="User-Agent a utiliser pour les requetes (defaut: %(default)s)")
    p_img.add_argument("--use-alt-json", dest="use_alt_json", action="store_true" if not USE_ALT_JSON else "store_false", help=("Activer" if not USE_ALT_JSON else "Desactiver") + " le renommage via product_sentences.json")
    p_img.add_argument("--alt-json-path", default=str(ALT_JSON_PATH), help="Chemin du fichier JSON pour le renommage (defaut: %(default)s)")
    p_img.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    p_img.add_argument("--max-threads", type=int, default=4, help="Nombre maximal de threads pour les telechargements (defaut: %(default)s)")
    p_img.add_argument("--jobs", type=int, default=1, help="Nombre maximal de pages a traiter en parallele (defaut: %(default)s)")
    p_img.set_defaults(use_alt_json=USE_ALT_JSON)
    p_img.set_defaults(func=lambda a, p=p_img: _run_images(a, p))

    # Description ----------------------------------------------------------
    p_desc = sub.add_parser("description", help="Scraper la description d'un produit")
    p_desc.add_argument("url", nargs="?", help="URL du produit (si absent, demande a l'execution)")
    p_desc.add_argument("-s", "--selector", default=DESCRIPTION_DEFAULT_SELECTOR, help="Selecteur CSS de la description (defaut: %(default)s)")
    p_desc.add_argument("-o", "--output", default="description.html", help="Fichier de sortie (defaut: %(default)s)")
    p_desc.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    p_desc.set_defaults(func=_run_description)

    # Price ---------------------------------------------------------------
    p_price = sub.add_parser("price", help="Scraper le prix d'un produit")
    p_price.add_argument("url", nargs="?", help="URL du produit (si absent, demande a l'execution)")
    p_price.add_argument("-s", "--selector", default=PRICE_DEFAULT_SELECTOR, help="Selecteur CSS du prix (defaut: %(default)s)")
    p_price.add_argument("-o", "--output", default="price.txt", help="Fichier de sortie (defaut: %(default)s)")
    p_price.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    p_price.set_defaults(func=_run_price)

    # Variants ------------------------------------------------------------
    p_var = sub.add_parser("variants", help="Extraire les variantes d'un produit")
    p_var.add_argument("url", nargs="?", help="URL du produit (si absent, demande a l'execution)")
    p_var.add_argument("-s", "--selector", default=VARIANT_DEFAULT_SELECTOR, help="Selecteur CSS des variantes")
    p_var.add_argument("-o", "--output", default="variants.txt", help="Fichier de sortie")
    p_var.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging")
    p_var.set_defaults(func=_run_variants)

    # GUI ----------------------------------------------------------------
    p_gui = sub.add_parser("gui", help="Lancer l'interface graphique")
    p_gui.set_defaults(func=_run_gui)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func")
    if func is None:
        parser.print_help()
        return
    if hasattr(func, "__call__"):
        func(args)


if __name__ == "__main__":
    main()
