# PEA Dashboard — M. Porta

## Déploiement sur Render.com

### Étape 1 — GitHub
1. Va sur github.com → New repository → nom : `pea-dashboard`
2. Upload les 4 fichiers : app.py, requirements.txt, render.yaml, Procfile
3. Commit

### Étape 2 — Render
1. Va sur render.com → New → Web Service
2. Connecte ton GitHub, sélectionne le repo `pea-dashboard`
3. Render détecte automatiquement la config (render.yaml)
4. Clique "Deploy"
5. Dans 2 minutes → URL type https://pea-dashboard-porta.onrender.com

### Mettre à jour les positions
Modifier les POSITIONS dans app.py et re-commit sur GitHub.
Render redéploie automatiquement.
