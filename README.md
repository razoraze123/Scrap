🧼 Universal Image Scraper – WooCommerce & Shopify
Un outil Python robuste et évolutif pour scraper automatiquement les images de produits sur des sites WooCommerce, Shopify et similaires.

⚙️ L’objectif est d’en faire une boîte à outils modulaire, avec une interface graphique (via PySide6), qui centralise tous les moteurs de scraping spécialisés.

📦 Fonctionnalités actuelles
✅ Téléchargement des images depuis une page produit
✅ Détection des images base64 intégrées (et sauvegarde locale)
✅ Nettoyage automatique des noms de produits / fichiers
✅ Sélecteur CSS personnalisable via la console
✅ Création automatique de sous-dossiers par produit
✅ Progression affichée avec tqdm
✅ Résumé final clair dans la console

🛠️ Dépendances
bash
Copier
Modifier
pip install selenium webdriver-manager tqdm requests

🗒️ Suivi des audits
Les rapports d'audit sont enregistrés dans `compte_rendu.txt`. Mettez ce fichier à jour à chaque nouvel audit. Pour consulter les derniers résultats, ouvrez `compte_rendu.txt` ou exécutez `cat compte_rendu.txt` dans votre terminal.
