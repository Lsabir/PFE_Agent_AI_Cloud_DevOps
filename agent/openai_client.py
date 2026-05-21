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
Tu es un expert Azure et Terraform. Tu travailles sur des projets Terraform EXISTANTS.
Ton rôle est d'analyser des demandes d'infrastructure et de produire uniquement
le code Terraform NOUVEAU compatible avec le projet existant.

Règles strictes :
- Utilise toujours azurerm provider >= 3.90 et Terraform >= 1.5
- Applique des tags sur toutes les ressources via merge(var.common_tags, {...})
- Ne duplique JAMAIS les ressources déjà dans le projet (azurerm_resource_group.rg existe déjà)
- Ne génère JAMAIS providers.tf, backend.tf, variables.tf, main.tf, outputs.tf
- Crée UN fichier .tf par ticket : ex. "pm5_vm.tf", "pm5_storage.tf" (nom en minuscules, sans espaces)
- Resource group : TOUJOURS utiliser azurerm_resource_group.rg.name et .location (déjà dans main.tf)
- Location : var.location
- Tags : merge(var.common_tags, { environment = var.environment })
- VM Linux : nécessite VNet/subnet — réutilise azurerm_virtual_network.vnet et azurerm_subnet.agent si présents dans network.tf, sinon crée-les dans le même fichier ticket
- VM : admin_ssh_key { username = "azureuser" public_key = var.ssh_public_key }
- Storage : resource_group_name = azurerm_resource_group.rg.name
- Pas de secrets en dur ; pas de provider/version blocks dans les fichiers ticket
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

    def generate_terraform(
        self,
        analysis: InfraAnalysis,
        existing_tf: dict[str, str] | None = None,
        issue_key: str = "ticket",
    ) -> dict[str, str]:
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

        existing_files = list(existing_tf.keys()) if existing_tf else []

        existing_context = ""
        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
PROJET TERRAFORM EXISTANT — fichiers déjà présents (NE PAS régénérer) :
{existing_files}

Contenu des fichiers existants :
{files_summary}

RÈGLE CRITIQUE : Ne génère PAS les fichiers listés ci-dessus.
Génère UNIQUEMENT des fichiers .tf NOUVEAUX nommés comme "{issue_key.lower()}_{{ressource}}.tf" (ex: {issue_key.lower()}_vm.tf).
NE PAS nommer les fichiers : main.tf, providers.tf, backend.tf, variables.tf, outputs.tf.
Réutilise OBLIGATOIREMENT : azurerm_resource_group.rg, var.location, var.common_tags, var.naming_prefix, var.ssh_public_key (pour VM).
Si network.tf existe : réutilise azurerm_virtual_network.vnet et azurerm_subnet.agent pour les VM.
Si de nouvelles variables sont nécessaires : fichier "{issue_key.lower()}_variables.tf" uniquement.
"""
        else:
            existing_context = """
Génère un projet Terraform complet avec : providers.tf, variables.tf, main.tf, outputs.tf, terraform.tfvars.example
"""

        prompt = f"""
{'Ajoute au projet Terraform existant' if existing_tf else 'Crée un nouveau projet Terraform Azure pour'} les ressources suivantes.
{existing_context}
Projet : {analysis.project_name}
Environnement : {analysis.environment}
Région : {analysis.location}
Préfixe : {analysis.naming_prefix}
Tags : {json.dumps(analysis.tags)}
Ressources à créer : {resources_desc}

Retourne un JSON {{nom_fichier: contenu_hcl}} avec AU MOINS un fichier .tf contenant les ressources demandées.
Clés JSON = noms de fichiers SANS préfixe terraform/ (ex: "pm5_vm.tf" pas "terraform/pm5_vm.tf").

{"Génère UNIQUEMENT les nouveaux fichiers — pas de doublons avec l'existant." if existing_tf else ""}
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
