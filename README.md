# Système expert et algorithmes de recherche

**Étudiant :** Amen Allah Hadded  
**Classe :** II2F  
**Matière :** Intelligence artificielle et apprentissage automatique  

## Présentation

Ce projet contient deux modules :

1. un système expert pour le diagnostic de pannes automobiles ;
2. un module de recherche dans des graphes orientés et pondérés.

L'application possède une interface graphique réalisée avec Tkinter.

## Installation et lancement

Le projet utilise uniquement Python et Tkinter. Aucune bibliothèque externe
n'est nécessaire.

```powershell
python main.py
```

Pour régénérer la base de connaissances :

```powershell
python converter.py automotive_faults_aktc_obike_et_al.json knowledge_base.json
```

## Organisation des fichiers

| Fichier                                   | Description                                         |
| ----------------------------------------- | --------------------------------------------------- |
| `main.py`                                 | Fenêtre principale et interfaces Tkinter            |
| `engine.py`                               | Chaînage avant, chaînage arrière et arbre de preuve |
| `converter.py`                            | Conversion du JSON automobile en règles             |
| `search_engine.py`                        | Graphe et algorithmes de recherche                  |
| `automotive_faults_aktc_obike_et_al.json` | Données automobiles d'origine                       |
| `knowledge_base.json`                     | Base de connaissances utilisée par l'application    |

## Système expert

Le diagnostic suit le raisonnement suivant :

```text
Symptômes → Suspect → Résultat d'un test → Panne
```

Le fichier automobile contient les catégories, les sous-catégories, les
symptômes et les étapes de diagnostic.

### Source du dataset

Le dataset automobile utilisé dans ce projet est disponible sur Zenodo :

[https://zenodo.org/records/15626055](https://zenodo.org/records/15626055)

Le convertisseur crée :

- des faits de type `symptom` ;
- des faits de type `test` et `test_ok` ;
- des faits de type `suspect` ;
- des faits de type `fault` ;
- des règles d'inférence ;
- des scénarios de démonstration.

Les symptômes d'une même sous-catégorie sont regroupés avec l'opérateur
`any`, ce qui correspond à un `OU`. Les conditions `all`, `any`, `not` et
`fact` sont disponibles dans les règles.

### Chaînage avant

Le moteur part des faits initiaux et applique les règles dont les conditions
sont satisfaites. Les nouveaux faits sont ajoutés jusqu'à trouver l'objectif
ou jusqu'à ce qu'aucune règle ne soit applicable.

### Chaînage arrière

Le moteur part de l'objectif et recherche les règles capables de le démontrer.
Il remonte ensuite vers les conditions nécessaires et peut poser des questions
à l'utilisateur pour les faits inconnus.

## Recherche dans les graphes

L'utilisateur peut :

- créer, modifier et supprimer des sommets ;
- créer, modifier et supprimer des arcs orientés ;
- donner un coût à chaque arc ;
- définir une heuristique `h(n)` ;
- choisir un sommet initial et un sommet objectif ;
- observer la frontière, les sommets explorés et le chemin final.

### Algorithmes non informés

- Recherche en largeur d'abord (BFS)
- Recherche en profondeur d'abord (DFS)
- Recherche à coût uniforme (UCS)
- Recherche à profondeur limitée (DLS)
- Approfondissement itératif (IDS)

### Algorithmes informés

- Recherche gloutonne (Greedy)
- A\*
- Simplified Memory-Bounded A* (SBA*)
- Recursive Best-First Search (RBFS)

Le graphe d'exemple contient les arcs suivants :

```text
S → A : 2
S → D : 4
S → E : 5
A → B : 3
A → E : 1
B → C : 2
C → G : 3
D → G : 9
E → G : 5
```

Le chemin `S → E → G` possède donc un coût de `10`.

## Base de connaissances

La base générée contient :

- `catalog` et `facts` : les faits avec leur type et leur identifiant ;
- `rules` : les règles utilisées par le moteur ;
- `scenarios` : les faits initiaux et l'objectif d'un scénario ;
- `initial_facts` et `demo_goal` : les valeurs utilisées par l'interface.

Les fichiers `automotive_faults_aktc_obike_et_al.json` et
`knowledge_base.json` sont des données du projet et non des fichiers Python.
