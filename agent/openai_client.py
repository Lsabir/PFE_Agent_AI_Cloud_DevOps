"""
openai_client.py — Interface avec Azure OpenAI
Analyse la description, identifie les ressources et génère le code Terraform.
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from openai import AzureOpenAI

from agent.config import AgentConfig


# ── Structures de données ──────────────────────────────────────────────────────

@dataclass
class ResourceSpec:
    """Représente une ressource Azure identifiée depuis la description."""
    type: str           # "vm", "database", "storage", "network", "keyvault", "openai"
    name: str           # nom logique
    parameters: dict = field(default_factory=dict)


@dataclass
class InfraAnalysis:
    """Résultat de l'analyse de la description par le LLM."""
    summary: str                              # résumé humain de ce qui sera créé
    project_name: str                         # nom du projet (slug)
    environment: str                          # dev / staging / prod
    location: str                             # région Azure
    resources: list[ResourceSpec] = field(default_factory=list)
    naming_prefix: str = "infra-prov"
    tags: dict = field(default_factory=dict)


# ── Système prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Tu es un expert Azure et Terraform. Ton rôle est d'analyser des demandes
d'infrastructure en langage naturel et de produire :
1. Une analyse JSON structurée des ressources Azure à créer.
2. Un code Terraform complet, PLAT (sans modules) et conforme aux bonnes pratiques.

Règles strictes :
- Utilise toujours azurerm provider >= 3.90 et Terraform >= 1.5
- Applique des tags sur toutes les ressources (project, environment, owner)
- N'utilise JAMAIS de modules externes ou locaux. Déclare TOUTES les ressources directement dans main.tf.
- Nomme les ressources avec un préfixe configurable via variable
- Externalise toutes les valeurs dans variables.tf avec des descriptions claires
- Ne mets jamais de secrets ou de mots de passe en dur dans le code
- Génère un outputs.tf avec les sorties importantes
- Respecte le principe du moindre privilège pour les rôles RBAC
- Active soft_delete sur Key Vault, disable public access sur les services sensibles
"""


# ── Client OpenAI ──────────────────────────────────────────────────────────────

class OpenAIClient:

    def __init__(self, config: AgentConfig):
        self.client = AzureOpenAI(
            azure_endpoint=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
            api_version=config.azure_openai_api_version,
        )
        self.deployment = config.azure_openai_deployment
        self.config = config

    # ── Analyse de la description ──────────────────────────────────────────────

    def analyze_description(self, description: str, existing_tf: dict[str, str] | None = None) -> InfraAnalysis:
        """
        Envoie la description au LLM et récupère une analyse JSON structurée
        des ressources Azure à créer.
        existing_tf : fichiers .tf existants du projet (peut être vide ou None).
        """
        existing_context = ""
        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content[:800]}{'...' if len(content) > 800 else ''}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
CONTEXTE — Infrastructure déjà déployée dans ce projet :
{files_summary}

Tiens compte de ces ressources existantes : ne les recrée pas, réutilise leurs
noms/IDs si la nouvelle demande en dépend, et signale toute mise à jour nécessaire.
"""

        prompt = f"""
Analyse la demande d'infrastructure suivante et retourne UNIQUEMENT un JSON valide.
{existing_context}
Demande : {description}

Format JSON attendu :
{{
  "summary": "Résumé clair de ce qui sera créé",
  "project_name": "slug-sans-espaces",
  "environment": "dev|staging|prod",
  "location": "germanywestcentral",
  "naming_prefix": "projet-env",
  "tags": {{"project": "...", "environment": "...", "owner": "devops-team"}},
  "resources": [
    {{
      "type": "vm|database|storage|network|keyvault|openai|container|aks",
      "name": "nom-logique",
      "parameters": {{
        "vm_size": "Standard_B2s",
        "os": "ubuntu-22.04",
        "...": "..."
      }}
    }}
  ]
}}

Inclus TOUJOURS un réseau (type: "network") si d'autres ressources en ont besoin.
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)
        

        resources = [
            ResourceSpec(
                type=r["type"],
                name=r["name"],
                parameters=r.get("parameters", {}),
            )
            for r in data.get("resources", [])
        ]

        return InfraAnalysis(
            summary=data.get("summary", ""),
            project_name=data.get("project_name", "infra-projet"),
            environment=data.get("environment", self.config.default_environment),
            location=data.get("location", self.config.default_location),
            naming_prefix=data.get("naming_prefix", self.config.naming_prefix),
            tags=data.get("tags", {}),
            resources=resources,
        )

    # ── Génération du code Terraform ───────────────────────────────────────────

    def generate_terraform(self, analysis: InfraAnalysis, existing_tf: dict[str, str] | None = None) -> dict[str, str]:
        """
        Génère les fichiers Terraform complets basés sur l'analyse.
        Retourne un dict {nom_fichier: contenu}.
        existing_tf : fichiers .tf existants à fusionner/mettre à jour.
        """
        resources_desc = json.dumps(
            [{"type": r.type, "name": r.name, "parameters": r.parameters}
             for r in analysis.resources],
            indent=2
        )

        existing_context = ""
        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
FICHIERS TERRAFORM EXISTANTS (à mettre à jour, ne pas dupliquer les ressources) :
{files_summary}

Fusionne les nouvelles ressources avec l'existant. Conserve les ressources déjà
présentes telles quelles, ajoute uniquement ce qui est nouveau.
"""

        prompt = f"""
Génère un projet Terraform Azure COMPLET pour les ressources suivantes.
{existing_context}
Projet : {analysis.project_name}
Environnement : {analysis.environment}
Région : {analysis.location}
Préfixe de nommage : {analysis.naming_prefix}
Tags : {json.dumps(analysis.tags)}
Ressources à créer : {resources_desc}

Génère EXACTEMENT les fichiers suivants, retourne un JSON avec le nom du fichier
comme clé et le contenu HCL comme valeur :

{{
  "providers.tf": "...",
  "variables.tf": "...",
  "main.tf": "...",
  "outputs.tf": "...",
  "terraform.tfvars.example": "..."
}}

Règles obligatoires :
1. providers.tf : azurerm >= 3.90, Terraform >= 1.5, backend azurerm avec
   commentaire indiquant les variables à renseigner (resource_group_name,
   storage_account_name, container_name, key)
2. variables.tf : TOUTES les valeurs configurables en variables avec description,
   type et default si applicable. NE JAMAIS mettre de secrets comme default.
3. main.tf : déclare TOUTES les ressources Azure (resource group, vnet, subnets,
   vm, etc.) directement dans ce fichier. NE PAS utiliser de blocs 'module'.
   Utilise des locals pour les tags.
4. outputs.tf : exports utiles (IDs, URIs, IPs, noms)
5. terraform.tfvars.example : exemple de fichier tfvars avec des valeurs
   fictives et des commentaires explicatifs. PAS de vraies valeurs sensibles.

Bonne pratique RBAC : si une VM est créée, active SystemAssigned Managed Identity.
Bonne pratique réseau : si services PaaS, utilise Private Endpoints.
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        files = json.loads(raw)

        # Ajoute le README généré automatiquement
        files["README.md"] = self._generate_readme(analysis, list(files.keys()))

        return files

    # ── Génération du README ───────────────────────────────────────────────────

    def _generate_readme(self, analysis: InfraAnalysis, tf_files: list[str]) -> str:
        resources_list = "\n".join(
            f"- **{r.type.upper()}** : `{r.name}`" for r in analysis.resources
        )
        return f"""# Infrastructure : {analysis.project_name}

> Généré automatiquement par l'Agent IA DevOps

## Résumé

{analysis.summary}

## Ressources Azure créées

{resources_list}

## Paramètres

| Paramètre | Valeur |
|-----------|--------|
| Région | `{analysis.location}` |
| Environnement | `{analysis.environment}` |
| Préfixe | `{analysis.naming_prefix}` |

## Déploiement

```bash
# 1. Copier et renseigner les variables
cp terraform.tfvars.example terraform.tfvars
# Editer terraform.tfvars avec vos vraies valeurs

# 2. Initialiser Terraform
terraform init

# 3. Vérifier la configuration
terraform validate

# 4. Voir le plan
terraform plan -var-file=terraform.tfvars

# 5. Appliquer (après validation humaine)
terraform apply -var-file=terraform.tfvars
```

## Fichiers générés

{chr(10).join(f'- `{f}`' for f in tf_files)}

## Tags appliqués

```hcl
{json.dumps(analysis.tags, indent=2)}
```
"""
