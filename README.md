# Actu Poster — version GitHub Actions

Cette version ne garde plus un processus Python actif comme sur Railway. Chaque
script fait **une seule tâche, sauvegarde son état, puis s'arrête**. GitHub
Actions se charge de le relancer selon les horaires définis dans
`.github/workflows/`.

## Ce qui a été adapté

- `main.py` : publie au maximum une actualité football puis quitte.
- `main2.py` : publie au maximum une actualité cinéma puis quitte.
- `main3.py` : génère les pronostics du jour puis quitte.
- `bot.py` : alias de compatibilité vers le nouveau `main.py`.
- Les boucles infinies et la dépendance au scheduler Railway ont été supprimées.
- L'historique anti-doublon est conservé entre deux runners éphémères grâce au
  cache GitHub Actions, séparément pour chaque service.
- Tous les tokens et clés sont maintenant lus depuis les secrets GitHub.
- Le fichier sensible `session_name.session` n'est pas inclus.
- Les workflows peuvent aussi être lancés manuellement depuis l'onglet
  **Actions**.

## Installation rapide

1. Créez de préférence un dépôt GitHub **privé**.
2. Placez **le contenu de ce dossier** à la racine du dépôt, y compris le
   dossier caché `.github`.
3. Dans GitHub, ouvrez **Settings → Secrets and variables → Actions**.
4. Cliquez sur **New repository secret** et ajoutez les secrets nécessaires.
5. Donnez au bot Telegram le rôle d'administrateur dans chacun des trois canaux,
   avec l'autorisation de publier des messages.
6. Ouvrez **Actions**, choisissez un workflow et cliquez sur **Run workflow**
   pour effectuer le premier test.

## Secrets nécessaires

| Secret | Obligatoire | Utilisation |
| --- | --- | --- |
| `BOT_TOKEN` | Oui | Token obtenu auprès de BotFather ; le même bot peut publier dans les trois canaux. |
| `FOOTBALL_CHANNEL_ID` | Oui | Canal réservé aux actualités football. |
| `CINEMA_CHANNEL_ID` | Oui | Canal réservé aux films et séries. |
| `PREDICTIONS_CHANNEL_ID` | Oui | Canal réservé aux pronostics. |
| `DEEPSEEK_API_KEY` | Non | Active l'analyse DeepSeek ; sinon l'analyse locale reste utilisée. |
| `API_FOOTBALL_KEY` | Non | Requis uniquement pour `red_cards.py` et `match_summary.py`. |

Les trois secrets de canal doivent contenir trois destinations différentes,
par exemple `@actu_foot`, `@films_series` et `@pronostics`. Un identifiant privé
du type `-1001234567890` fonctionne également.

Si chaque canal utilise aussi son propre bot, ajoutez les tokens spécialisés
suivants. Ils ont priorité sur `BOT_TOKEN` :

- `FOOTBALL_BOT_TOKEN`
- `CINEMA_BOT_TOKEN`
- `PREDICTIONS_BOT_TOKEN`

Ne placez jamais une vraie clé dans `.env.example` ou directement dans un
workflow YAML.

### Diagnostic Telegram sans publier

Un workflow manuel **Diagnostic Telegram** est fourni. Il vérifie les trois
associations bot → canal avec `getMe` et `getChatMember`, sans envoyer de post.
Dans **Actions → Diagnostic Telegram → Run workflow**, le journal indique aussi
si le token réellement utilisé vient du secret spécialisé (`FOOTBALL_BOT_TOKEN`,
`CINEMA_BOT_TOKEN`, `PREDICTIONS_BOT_TOKEN`) ou du `BOT_TOKEN` commun.

Une erreur `Forbidden: bot is not a member of the channel chat` signifie que le
bot correspondant au token actif doit être ajouté **à ce canal précis** comme
administrateur avec le droit de publier, ou que le secret de canal/token pointe
vers la mauvaise paire.

## Horaires livrés

Les horaires utilisent le fuseau `Africa/Lome` :

| Workflow | Horaire par défaut |
| --- | --- |
| Actualités football | Toutes les 30 minutes, à `:07` et `:37` |
| Actualités cinéma | Toutes les 30 minutes, à `:22` et `:52` |
| Pronostics | Tous les jours à `06:13` |

Les minutes ont volontairement été décalées du début d'heure pour réduire les
retards liés aux périodes de forte charge. Pour modifier une fréquence, éditez
le bloc `on.schedule` du workflow correspondant.

## Vérification locale

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell : .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest -q
python main.py --dry-run
python main2.py --dry-run
DRY_RUN=1 python main3.py
```

Le mode `--dry-run`/`DRY_RUN=1` affiche les messages sans les envoyer et sans
modifier l'historique. L'option `--force`, ou l'option **force** du lancement
manuel, permet d'ignorer l'historique.

## État persistant et doublons

Un runner GitHub Actions est supprimé à la fin de chaque tâche. Les fichiers
`.state/*.json` sont donc restaurés et sauvegardés avec `actions/cache`. Le
projet garde jusqu'à 500 identifiants RSS par canal. Le workflow des pronostics
mémorise également la date du dernier envoi réussi afin d'éviter une double
publication dans la même journée.

Un cache GitHub n'est pas une base de données garantie à vie. S'il est supprimé
manuellement ou évincé, un ancien article peut exceptionnellement être republié.
Pour une garantie absolue, remplacez ce cache par une base externe.

## Scripts Telegram utilisateur

`teste.py` et `user.py` ne restent plus connectés en continu : ils récupèrent
ponctuellement les derniers messages puis s'arrêtent. Ils sont facultatifs et
nécessitent :

```bash
python -m pip install -r requirements-tools.txt
```

ainsi que les secrets `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` et
`TELEGRAM_STRING_SESSION`. Ne commitez jamais un fichier `*.session`.

## Limite importante de GitHub Actions

GitHub Actions convient aux publications périodiques, mais pas à une
surveillance réellement instantanée 24 h/24. Une tâche planifiée peut démarrer
avec du retard en période de forte charge. Les alertes à la seconde près
(carton rouge, nouveau message Telegram en direct, etc.) doivent rester sur un
hébergeur de processus continu ou être converties en vérifications périodiques.

## Sécurité avant mise en ligne

Le projet d'origine contenait un `API_HASH` en clair et un fichier de session
Telegram. Ils ne sont pas repris ici. Si ces éléments ont déjà été publiés ou
partagés, révoquez la session depuis **Telegram → Paramètres → Appareils** avant
d'utiliser ce dépôt.


## Protection contre les erreurs de traduction

Le bot football utilise désormais un flux RSS francophone (Foot Mercato) et ne dépend plus de Google Translate pour ses publications. Le moteur commun détecte aussi les réponses du type `Error 500 / Server Error / Please try again later` et refuse de les publier sur Telegram. Le flux cinéma Allociné étant déjà en français, sa traduction automatique est également désactivée.

## Images obligatoires pour les actualités

Les workflows football et cinéma ne publient **jamais** un article sans vraie image source. L'ordre de recherche est :
1. image fournie directement par le flux RSS ;
2. image OpenGraph/Twitter (`og:image`, `twitter:image`) de la page de l'article.

Si aucune image exploitable n'est trouvée, l'article est ignoré et le moteur essaie l'article suivant. Si aucun nouvel article avec image n'est disponible, aucune publication n'est envoyée. **Aucune image de secours n'est générée.**

Les images web existantes peuvent être normalisées en JPEG avant l'envoi afin d'éviter les formats, dimensions ou poids qui provoquent des erreurs Telegram.

## Correction CI / imports Pytest

Le workflow de vérification définit explicitement la racine du dépôt dans `PYTHONPATH`, vérifie la présence de `news_publisher.py` et `main3.py`, puis lance les tests avec `python -m pytest -q`. Le fichier `pytest.ini` et `tests/conftest.py` garantissent également que les modules placés à la racine restent importables quel que soit le mode de lancement de Pytest.
