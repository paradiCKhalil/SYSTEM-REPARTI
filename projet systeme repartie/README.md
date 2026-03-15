# Systeme distribue de supervision reseau

Ce projet implemente une architecture client-serveur de supervision conforme au sujet:

- agent de supervision Python envoyant periodiquement des metriques systeme
- serveur TCP multi-clients base sur un pool de threads
- protocole applicatif JSON sur sockets TCP
- stockage SQLite avec pool de connexions
- journalisation des alertes et detection des noeuds inactifs
- interface console cote serveur pour consulter les donnees et envoyer des commandes UP/DOWN

## Fichiers principaux

- `server.py` : serveur central de supervision
- `client.py` : agent de supervision a lancer sur chaque noeud
- `load_test.py` : lanceur de demonstration multi-clients
- `protocol.py` : encodage, lecture et validation simple des messages JSON
- `database.py` : pool de connexions SQLite et acces aux donnees
- `schema.sql` : script de creation de la base de donnees

## Installation

```bash
cd "projet systeme repartie"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancer le serveur

```bash
cd "projet systeme repartie"
python3 server.py --host 0.0.0.0 --port 5000 --db supervision.db
```

Pour lancer le serveur en arriere-plan ou pendant des tests automatises, desactivez la console:

```bash
cd "projet systeme repartie"
python3 server.py --host 0.0.0.0 --port 5000 --db supervision.db --no-console
```

Commandes disponibles dans la console du serveur:

- `nodes` : liste des noeuds connus
- `metrics [node_id]` : affiche les dernieres metriques
- `alerts` : affiche les alertes recentes
- `events` : affiche les evenements recents
- `up <node_id> <service>` : force un service a actif chez le client connecte
- `down <node_id> <service>` : force un service a inactif chez le client connecte
- `quit` : arret du serveur

## Lancer un client

```bash
cd "projet systeme repartie"
python3 client.py --host 127.0.0.1 --port 5000 --interval 10 --node-id node-1
```

Vous pouvez lancer plusieurs clients dans plusieurs terminaux, par exemple:

```bash
python3 client.py --host 127.0.0.1 --port 5000 --interval 5 --node-id node-a
python3 client.py --host 127.0.0.1 --port 5000 --interval 5 --node-id node-b
python3 client.py --host 127.0.0.1 --port 5000 --interval 5 --node-id node-c
```

## Demonstration de charge

Pour simuler rapidement 10, 50 ou 100 agents sans ouvrir autant de terminaux, utilisez le lanceur de charge:

```bash
cd "projet systeme repartie"
python3 load_test.py --host 127.0.0.1 --port 5000 --count 10 --duration 30 --interval 5
```

Exemples utiles:

```bash
python3 load_test.py --host 127.0.0.1 --port 5000 --count 50 --duration 45 --interval 5
python3 load_test.py --host 127.0.0.1 --port 5000 --count 100 --duration 60 --interval 10
```

Chaque client est journalise dans le dossier `load-test-logs/` avec un fichier par noeud.

## Protocole de communication

Tous les messages sont envoyes en JSON, un message par ligne.

Exemples:

```json
{"type":"hello","node_id":"node-a","timestamp":"2026-03-15T12:00:00+00:00","os_name":"Linux","cpu_model":"x86_64"}
```

```json
{"type":"metrics","node_id":"node-a","timestamp":"2026-03-15T12:00:10+00:00","metrics":{"node_id":"node-a","timestamp":"2026-03-15T12:00:10+00:00","os_name":"Linux","cpu_model":"x86_64","cpu_percent":17.3,"memory_percent":43.1,"disk_percent":61.0,"uptime_seconds":12880.2,"alert":false,"services":{"ssh":true,"nginx":false,"docker":true,"firefox":false,"chrome":false,"code":false},"ports":{"22":true,"80":false,"443":false,"3306":false}}}
```

```json
{"type":"command","node_id":"node-a","timestamp":"2026-03-15T12:01:00+00:00","command":"UP","service":"nginx"}
```

## Choix techniques

- `ThreadPoolExecutor` sert de pool de threads pour gerer plusieurs clients TCP simultanement.
- SQLite est utilise pour simplifier le livrable, avec un pool de connexions pour illustrer l'acces concurrent cote serveur.
- Les commandes `UP` et `DOWN` modifient l'etat logique des services cote agent. Elles ne tentent pas de demarrer un vrai service systeme, ce qui evite les problemes de permissions durant la demonstration.
- Les metriques CPU, memoire, disque et uptime sont reelles via `psutil`. Les services et ports sont detectes localement sur la machine cliente.

## Points a presenter dans le rapport

- architecture globale client-serveur
- protocole applicatif JSON et gestion des erreurs
- comparaison du choix de pool de threads
- justification du pool de connexions BD
- demonstration multi-clients avec 10, 50 et 100 agents si possible
- limites actuelles et pistes d'amelioration

## Limites actuelles

- l'interface d'administration est en console, pas en GUI
- la commande serveur agit sur un etat logique de service, pas sur systemd
- SQLite convient bien a une demo, mais pas a une charge tres elevee