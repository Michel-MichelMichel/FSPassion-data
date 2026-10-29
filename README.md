# FSPassion-data

**Français** · [English](#english)

Données publiques lues par [FS Passion](https://github.com/Michel-MichelMichel/FSPassion), gestionnaire de mods pour Farming Simulator :

- `dlc/dlc_catalog.json` : catalogue des DLC officiels, par version du jeu (nom du fichier, nom affiché, état, empreinte de l'icône) ;
- `dlc/icons_dlc_fs11/` … `dlc/icons_dlc_fs28/` : une icône par DLC.

FS Passion lit ces fichiers au plus une fois par jour, seulement si l'utilisateur l'autorise (Paramètres → Application → Connexion Internet), et ne télécharge que les icônes des DLC présents sur son PC. Aucune donnée n'est envoyée.

Un nouveau DLC n'oblige pas à publier une nouvelle version de FS Passion : il suffit d'ajouter son entrée au catalogue et son icône, puis de lancer `preparer_catalogue_dlc.bat` (dépôt FS Passion) avant la publication.

Les noms et les visuels des DLC appartiennent à GIANTS Software. Ils servent uniquement à reconnaître les DLC installés. FS Passion est un projet indépendant, non affilié à GIANTS Software. Farming Simulator est une marque de GIANTS Software.

---

## English

Public data read by [FS Passion](https://github.com/Michel-MichelMichel/FSPassion), a mod manager for Farming Simulator: the official DLC catalog (`dlc/dlc_catalog.json`) and one icon per DLC (`dlc/icons_dlc_fsXX/`). FS Passion reads them at most once a day, only with the user's consent, and only downloads the icons of DLC installed on their PC. No data is sent.

DLC names and artwork belong to GIANTS Software and are only used to identify installed DLC. FS Passion is an independent project, not affiliated with GIANTS Software. Farming Simulator is a trademark of GIANTS Software.
