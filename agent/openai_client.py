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

# Fichiers que l'agent peut modifier (jamais providers/backend = state & auth)
EDITABLE_TF_FILES = ("main.tf", "variables.tf", "outputs.tf", "network.tf")

SYSTEM_PROMPT = """
Tu es un expert Azure et Terraform. Tu MODIFIES un projet Terraform EXISTANT
pour réaliser une demande Jira — tu n'ajoutes pas de nouveaux fichiers .tf séparés.

Règles strictes :
- azurerm >= 3.90, Terraform >= 1.5
- MODIFIE uniquement les fichiers existants pertinents : main.tf, variables.tf, outputs.tf, network.tf
- Ne modifie JAMAIS providers.tf ni backend.tf
- Retourne le contenu COMPLET de chaque fichier modifié (fichier entier, pas un extrait ni un patch)
- CONSERVE tout le code existant non concerné par le ticket ; ajoute/fusionne proprement
- Ne duplique pas azurerm_resource_group.rg s'il existe déjà
- Tags : merge(var.common_tags, { environment = var.environment })
- VM : réutilise azurerm_virtual_network.vnet / azurerm_subnet.agent de network.tf ; sinon complète network.tf
- VM : admin_ssh_key avec var.ssh_public_key, username "azureuser"
- Nouvelles variables → ajoute dans variables.tf (ne supprime pas les variables existantes)
- Nouveaux outputs → ajoute dans outputs.tf
- Pas de secrets en dur ; pas de blocs terraform/provider dans main.tf/network.tf
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
            editable = [f for f in existing_files if f in EDITABLE_TF_FILES or f not in ("providers.tf", "backend.tf")]
            existing_context = f"""
PROJET TERRAFORM EXISTANT — tu dois MODIFIER ces fichiers en place (pas de nouveaux fichiers .tf) :
{existing_files}

Fichiers modifiables pour ce ticket : {editable}
Interdit de modifier : providers.tf, backend.tf

Contenu actuel (à préserver et étendre) :
{files_summary}

RÈGLE CRITIQUE :
- Retourne un JSON {{nom_fichier: contenu_hcl_complet}} UNIQUEMENT pour les fichiers que tu as modifiés.
- Chaque valeur = fichier ENTIER prêt pour terraform validate (pas de fragment, pas de "...").
- Ticket Jira : {issue_key} — intègre les ressources demandées dans la structure existante.
- VM/storage/etc. → main.tf et/ou network.tf ; variables dans variables.tf ; outputs dans outputs.tf.
- Réutilise : azurerm_resource_group.rg, var.location, var.common_tags, var.naming_prefix.
"""
        else:
            existing_context = """
Génère un projet Terraform complet avec : providers.tf, variables.tf, main.tf, outputs.tf, terraform.tfvars.example
"""

        prompt = f"""
{'Modifie le projet Terraform existant' if existing_tf else 'Crée un nouveau projet Terraform Azure'} pour réaliser ce ticket Jira.
{existing_context}
Projet : {analysis.project_name}
Environnement : {analysis.environment}
Région : {analysis.location}
Préfixe : {analysis.naming_prefix}
Tags : {json.dumps(analysis.tags)}
Ressources demandées : {resources_desc}

Retourne un JSON {{nom_fichier: contenu_hcl}}.
{"Clés = noms de fichiers EXISTANTS modifiés (ex: main.tf, network.tf, variables.tf). Pas de nouveau fichier pm5_xxx.tf." if existing_tf else "Crée providers.tf, variables.tf, main.tf, outputs.tf, network.tf si besoin."}
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=8000,
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
