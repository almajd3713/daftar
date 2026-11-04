# Votre application Daftar

Il faut Docker et Docker Compose sur la machine.

## Démarrer

```sh
./start
```

{{ACCESS}}

Au premier démarrage, créez le compte du propriétaire : vos données importées sont déjà chargées.

**N'utilisez jamais `docker compose down -v` : cela efface toutes les données.**

## Sauvegarder

```sh
./backup
```

Une sauvegarde est aussi faite chaque jour dans `backups/`, et les 14 dernières sont gardées.

**Une sauvegarde restée sur la même machine ne protège pas d'une panne.** {{OFFSITE}} Indiquez la destination dans `DAFTAR_OFFSITE`, dans le fichier `.env`, puis lancez chaque jour :

```sh
./offsite
```

Ces sauvegardes contiennent toutes vos données : gardez-les dans un endroit protégé.

## Restaurer

```sh
./restore backups/LE-FICHIER.dump
```

**Cela remplace toutes les données actuelles par celles de la sauvegarde.** Faites un essai lors de la remise de l'application, pour vérifier que vos sauvegardes fonctionnent.

## Gardez ce dossier en lieu sûr

Le fichier `.env` contient les mots de passe de l'application : ne le partagez pas. Si la machine est perdue, une nouvelle installation et une sauvegarde suffisent à tout retrouver, avec les mêmes comptes. Il faudra seulement se reconnecter.
