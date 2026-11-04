# Votre application Daftar

Il faut Docker et Docker Compose sur la machine.

## Démarrer

```sh
./start
```

Ouvrez ensuite <http://127.0.0.1:8080>. Au premier démarrage, créez le compte du propriétaire : vos données importées sont déjà chargées.

**Pour l'instant, l'application n'est accessible que depuis cette machine.** L'accès depuis d'autres appareils demande une connexion sécurisée (TLS), qui dépend de l'endroit où l'application sera installée.

## Sauvegarder

```sh
./backup
```

Une sauvegarde est aussi faite chaque jour dans `backups/`, et les 14 dernières sont gardées. **Copiez ce dossier ailleurs régulièrement** : s'il reste sur la même machine, une panne de disque emporte tout.

## Restaurer

```sh
./restore backups/LE-FICHIER.dump
```

**Cela remplace toutes les données actuelles par celles de la sauvegarde.** Faites un essai lors de la remise de l'application, pour vérifier que vos sauvegardes fonctionnent.

## Gardez ce dossier en lieu sûr

Le fichier `.env` contient les mots de passe de l'application. Ne le partagez pas et ne le perdez pas : sans lui, les comptes de vos utilisateurs ne fonctionnent plus, même après une restauration.
